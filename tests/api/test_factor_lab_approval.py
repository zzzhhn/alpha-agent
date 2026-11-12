import json
import time
from datetime import datetime, timezone

import asyncpg
import pytest
from jose import jwt

_SECRET = "test-secret-not-real-0123456789"


def _auth(sub: str = "1") -> dict:
    now = int(time.time())
    tok = jwt.encode({"sub": sub, "iat": now, "exp": now + 3600}, _SECRET, algorithm="HS256")
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture
def authed_client(client_with_db, monkeypatch):
    monkeypatch.setenv("NEXTAUTH_SECRET", _SECRET)
    return client_with_db


async def _seed_pending(applied_db, expression="rank(returns)", new_operators=None):
    conn = await asyncpg.connect(applied_db)
    try:
        return await conn.fetchval(
            "INSERT INTO factor_proposals "
            "(expression, new_operators, evidence, diagnostic) "
            "VALUES ($1, $2::jsonb, $3::jsonb, $4::jsonb) RETURNING id",
            expression,
            json.dumps(new_operators or []),
            json.dumps({"sharpes": [0.8, 0.7, 0.9], "ic_oos": 0.04,
                        "deflated_sharpe": 0.5, "baseline_sharpe": 0.3,
                        "n_folds": 3, "n_trials": 5,
                        "llm_rationale": "test", "operator_test_results": []}),
            json.dumps({"current_expression": "rank(returns)",
                        "weak_signal": "news_24h", "weak_signal_ic": 0.003,
                        "worst_fold_sharpe": None, "worst_fold_window": None,
                        "symptom_summary": "test"}),
        )
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_list_pending_proposals(client_with_db, applied_db):
    await _seed_pending(applied_db)
    body = client_with_db.get("/api/factor-lab/proposals").json()
    assert any(p["status"] == "pending" for p in body["proposals"])
    p = body["proposals"][0]
    assert p["evidence"]["n_folds"] == 3
    assert p["diagnostic"]["weak_signal"] == "news_24h"


@pytest.mark.asyncio
async def test_list_proposals_filters_by_status(client_with_db, applied_db):
    pid = await _seed_pending(applied_db)
    conn = await asyncpg.connect(applied_db)
    try:
        await conn.execute("UPDATE factor_proposals SET status='approved' WHERE id=$1", pid)
    finally:
        await conn.close()
    body = client_with_db.get("/api/factor-lab/proposals?status=approved").json()
    assert all(p["status"] == "approved" for p in body["proposals"])


@pytest.mark.asyncio
async def test_approve_writes_custom_expression_and_marks_approved(authed_client, applied_db):
    pid = await _seed_pending(applied_db, expression="rank(ts_mean(returns, 8))")
    r = authed_client.post(f"/api/factor-lab/proposals/{pid}/approve", headers=_auth())
    assert r.status_code == 200, r.text
    conn = await asyncpg.connect(applied_db)
    try:
        v = await conn.fetchval(
            "SELECT value FROM engine_config WHERE key='factor.custom_expression'"
        )
        assert json.loads(v) == "rank(ts_mean(returns, 8))"
        row = await conn.fetchrow(
            "SELECT status, decided_by FROM factor_proposals WHERE id=$1", pid,
        )
        assert row["status"] == "approved"
        assert row["decided_by"] == 1
    finally:
        await conn.close()


def test_approve_registers_new_operators_idempotently(authed_client, applied_db):
    """Two approvals with the same operator name must stay idempotent (count=1).

    Two sequential TestClient calls share the asyncpg pool singleton.  The
    pool is bound to the event loop created in the first call; that loop is
    closed when the call returns, so the second call must create a fresh pool
    on a fresh loop.  Reset the singleton between calls (mirrors the
    test_rollback_reverts_applied_change pattern in test_evolution_approval.py).
    """
    import asyncio

    import alpha_agent.storage.postgres as _pg

    new_op = {
        "name": "lf_test_op",
        "signature": "(x: ndarray) -> ndarray",
        "python_impl": "def lf_test_op(x): return x",
        "doc": "test",
    }
    pid1 = asyncio.run(_seed_pending(applied_db, new_operators=[new_op]))
    r1 = authed_client.post(f"/api/factor-lab/proposals/{pid1}/approve", headers=_auth())
    assert r1.status_code == 200

    # Reset pool so the second request gets a fresh pool on a fresh loop.
    _pg._pool = None
    _pg._pool_dsn = None

    pid2 = asyncio.run(_seed_pending(applied_db, new_operators=[new_op]))
    r2 = authed_client.post(f"/api/factor-lab/proposals/{pid2}/approve", headers=_auth())
    assert r2.status_code == 200

    async def _count(db_url):
        conn = await asyncpg.connect(db_url)
        try:
            return await conn.fetchval(
                "SELECT count(*) FROM extended_operators WHERE name='lf_test_op'"
            )
        finally:
            await conn.close()

    n = asyncio.run(_count(applied_db))
    assert n == 1  # idempotent


@pytest.mark.asyncio
async def test_approve_surfaces_refresh_allowed_ops_outcome(authed_client, applied_db):
    """The approve response must report refresh_error (null on success, string on
    failure). A non-null value means the AST validator will silently reject the
    new operator until refresh; the admin needs to see this immediately."""
    pid = await _seed_pending(applied_db)
    body = authed_client.post(
        f"/api/factor-lab/proposals/{pid}/approve", headers=_auth()
    ).json()
    assert "refresh_error" in body  # field always present; null on success
    assert body["refresh_error"] is None  # success path on the test DB


@pytest.mark.asyncio
async def test_reject_marks_rejected_without_engine_config(authed_client, applied_db):
    pid = await _seed_pending(applied_db)
    authed_client.post(f"/api/factor-lab/proposals/{pid}/reject", headers=_auth())
    conn = await asyncpg.connect(applied_db)
    try:
        st = await conn.fetchval("SELECT status FROM factor_proposals WHERE id=$1", pid)
        assert st == "rejected"
        n = await conn.fetchval(
            "SELECT count(*) FROM engine_config WHERE key='factor.custom_expression'"
        )
        assert n == 0
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_reject_404_on_non_pending(authed_client):
    r = authed_client.post("/api/factor-lab/proposals/999999/reject", headers=_auth())
    assert r.status_code == 404


def test_rollback_reverts_custom_expression(authed_client, applied_db):
    """Approve then rollback; verify factor.custom_expression reverts to None.

    Two sequential TestClient calls require a pool singleton reset between
    them (same loop-isolation issue as test_approve_registers_new_operators).
    Verification uses asyncio.run() to avoid mixing an async test body with
    TestClient's own event loop.
    """
    import asyncio

    import alpha_agent.storage.postgres as _pg

    pid = asyncio.run(_seed_pending(applied_db, expression="rank(returns)"))
    authed_client.post(f"/api/factor-lab/proposals/{pid}/approve", headers=_auth())

    # Reset pool so rollback request gets a fresh pool on a fresh loop.
    _pg._pool = None
    _pg._pool_dsn = None

    r = authed_client.post(f"/api/factor-lab/proposals/{pid}/rollback", headers=_auth())
    assert r.status_code == 200, r.text

    async def _verify(db_url):
        conn = await asyncpg.connect(db_url)
        try:
            return await conn.fetchval(
                "SELECT value FROM engine_config WHERE key='factor.custom_expression'"
            )
        finally:
            await conn.close()

    v = asyncio.run(_verify(applied_db))
    # Reverted to None (prior state before the only approval).
    assert v is None or json.loads(v) is None


@pytest.mark.asyncio
async def test_rollback_404_on_non_approved(authed_client, applied_db):
    pid = await _seed_pending(applied_db)
    # Still pending; rollback should 404.
    r = authed_client.post(f"/api/factor-lab/proposals/{pid}/rollback", headers=_auth())
    assert r.status_code == 404


async def test_factor_lab_group_proposals_by_expression(client_with_db, applied_db):
    zero = {"sharpes": [0, 0, 0], "ic_oos": 0}
    strongest_sharpe = {"sharpes": [1, 2, 3], "ic_oos": 0.03}
    strongest_ic = {"sharpes": [0.5, 0.5, 0.5], "ic_oos": 0.08}
    ic_only = {"sharpes": [0, 0, 0], "ic_oos": -0.01}
    data = [
        ("rank(close)", strongest_sharpe, 1, "pending"),
        ("rank( close )", strongest_ic, 2, "pending"),
        ("rank(close)", zero, 3, "pending"),
        ("zscore(volume)", ic_only, 4, "pending"),
        ("rank(volume)", zero, 5, "pending"),
        ("adv20", {}, 6, "pending"),
        ("rank(close)", strongest_sharpe, 7, "rejected"),
    ]
    conn = await asyncpg.connect(applied_db)
    try:
        ids = []
        for expression, evidence, day, status in data:
            ids.append(await conn.fetchval(
                "INSERT INTO factor_proposals (expression, evidence, diagnostic, created_at, status) "
                "VALUES ($1, $2::jsonb, '{}'::jsonb, $3, $4) RETURNING id",
                expression, json.dumps(evidence), datetime(2026, 11, day, tzinfo=timezone.utc), status,
            ))
    finally:
        await conn.close()

    response = client_with_db.get("/api/factor-lab/proposals?status=pending&group=expression")
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["proposals"]) == 6
    assert all(p["status"] == "pending" for p in body["proposals"])
    groups = body["groups"]
    assert [g["canonical_expression"] for g in groups] == [
        "zscore(volume)", "rank(close)", "adv20", "rank(volume)",
    ]
    assert groups[0]["has_validation_evidence"] is True  # IC alone, including negative IC
    assert groups[0]["best_ic_oos"] == -0.01
    ranked = groups[1]
    assert ranked == {
        "canonical_expression": "rank(close)",
        "count": 3,
        "proposal_ids": [ids[2], ids[1], ids[0]],
        "latest_id": ids[2],
        "first_created_at": "2026-11-01T00:00:00+00:00",
        "last_created_at": "2026-11-03T00:00:00+00:00",
        "has_validation_evidence": True,
        "best_mean_sharpe": 2.0,
        "best_ic_oos": 0.08,
        "latest_evidence": zero,
    }
    assert groups[2]["has_validation_evidence"] is False
    assert groups[2]["best_mean_sharpe"] is None
    assert groups[2]["best_ic_oos"] is None
    assert groups[3]["has_validation_evidence"] is False


@pytest.mark.parametrize("group", [None, "expression"])
async def test_factor_lab_grouping_is_bounded_and_default_unchanged(client_with_db, applied_db, group):
    conn = await asyncpg.connect(applied_db)
    try:
        await conn.execute(
            "INSERT INTO factor_proposals (expression, evidence, diagnostic) "
            "SELECT 'rank(close)', '{}'::jsonb, '{}'::jsonb FROM generate_series(1, 501)"
        )
    finally:
        await conn.close()
    url = "/api/factor-lab/proposals" + ("?group=expression" if group else "")
    response = client_with_db.get(url)
    assert response.status_code == 200, response.text
    body = response.json()
    if group:
        assert len(body["proposals"]) == 500
        assert body["groups"][0]["count"] == 500
        assert body["groups"][0]["latest_id"] == 501
        assert body["groups"][0]["proposal_ids"] == list(range(501, 1, -1))
    else:
        assert set(body) == {"proposals"}
        assert len(body["proposals"]) == 200


@pytest.mark.parametrize("query", ["group=other", "group=expression&status=other"])
def test_factor_lab_grouping_rejects_invalid_filters(client_with_db, query):
    assert client_with_db.get(f"/api/factor-lab/proposals?{query}").status_code == 400


async def test_factor_lab_batch_reject_pending_only(authed_client, applied_db):
    pending = await _seed_pending(applied_db)
    approved = await _seed_pending(applied_db)
    rejected = await _seed_pending(applied_db)
    untouched = await _seed_pending(applied_db)
    conn = await asyncpg.connect(applied_db)
    try:
        await conn.execute(
            "UPDATE factor_proposals SET status='approved', decided_at=now(), decided_by=9 "
            "WHERE id=$1", approved,
        )
        await conn.execute(
            "UPDATE factor_proposals SET status='rejected', decided_at=now(), decided_by=8 "
            "WHERE id=$1", rejected,
        )
        before = {row["id"]: dict(row) for row in await conn.fetch("SELECT * FROM factor_proposals")}
    finally:
        await conn.close()

    response = authed_client.post(
        "/api/factor-lab/proposals/reject-batch", headers=_auth(),
        json={"proposal_ids": [rejected, 999999, pending, approved]},
    )
    assert response.status_code == 200, response.text
    assert response.json() == {
        "rejected": 1, "skipped_not_pending": [rejected, approved], "not_found": [999999],
    }
    conn = await asyncpg.connect(applied_db)
    try:
        after = {row["id"]: dict(row) for row in await conn.fetch("SELECT * FROM factor_proposals")}
        assert set(after) == set(before)  # no deletion or insertion
        expected = {**before[pending], "status": "rejected", "decided_by": 1,
                    "decided_at": after[pending]["decided_at"]}
        assert after[pending] == expected
        assert after[pending]["decided_at"] is not None
        for pid in (approved, rejected, untouched):
            assert after[pid] == before[pid]
        assert await conn.fetchval("SELECT count(*) FROM engine_config") == 0
    finally:
        await conn.close()


@pytest.mark.parametrize("sub", [None, "2"])
async def test_factor_lab_batch_reject_requires_admin(authed_client, applied_db, sub):
    pid = await _seed_pending(applied_db)
    response = authed_client.post(
        "/api/factor-lab/proposals/reject-batch", headers=_auth(sub) if sub else {},
        json={"proposal_ids": [pid]},
    )
    assert response.status_code == (403 if sub else 401)
    conn = await asyncpg.connect(applied_db)
    try:
        row = await conn.fetchrow("SELECT status, decided_at, decided_by FROM factor_proposals WHERE id=$1", pid)
        assert dict(row) == {"status": "pending", "decided_at": None, "decided_by": None}
    finally:
        await conn.close()


@pytest.mark.parametrize("ids", [[], list(range(501)), [1, 1], ["1"], [1.5], [True]])
def test_factor_lab_batch_reject_validates_ids(authed_client, ids):
    response = authed_client.post(
        "/api/factor-lab/proposals/reject-batch", headers=_auth(), json={"proposal_ids": ids},
    )
    assert response.status_code == 422, response.text


async def test_factor_lab_batch_reject_accepts_500_ids(authed_client, applied_db):
    conn = await asyncpg.connect(applied_db)
    try:
        rows = await conn.fetch(
            "INSERT INTO factor_proposals (expression, evidence, diagnostic) "
            "SELECT 'rank(close)', '{}'::jsonb, '{}'::jsonb FROM generate_series(1, 500) RETURNING id"
        )
    finally:
        await conn.close()
    response = authed_client.post(
        "/api/factor-lab/proposals/reject-batch", headers=_auth(),
        json={"proposal_ids": [row["id"] for row in rows]},
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"rejected": 500, "skipped_not_pending": [], "not_found": []}
    conn = await asyncpg.connect(applied_db)
    try:
        assert await conn.fetchval("SELECT count(*) FROM factor_proposals WHERE status='rejected'") == 500
        assert await conn.fetchval("SELECT count(DISTINCT decided_at) FROM factor_proposals") == 1
    finally:
        await conn.close()


async def _set_custom_expression(applied_db, expression):
    conn = await asyncpg.connect(applied_db)
    try:
        await conn.execute(
            "INSERT INTO engine_config (key, value, updated_at, updated_by) "
            "VALUES ('factor.custom_expression', $1::jsonb, now(), 2) "
            "ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value",
            json.dumps(expression),
        )
    finally:
        await conn.close()


async def test_restore_preset_clears_custom_expression_and_journals(authed_client, applied_db):
    from alpha_agent.signals.factor import SHORT_TERM_FACTOR_EXPR

    custom = "group_neutralize(zscore(ts_zscore(volume,20)),sector)"
    await _set_custom_expression(applied_db, custom)
    response = authed_client.post("/api/factor-lab/live-expression/restore-preset", headers=_auth())
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["changed"] is True
    assert body["previous_expression"] == custom
    assert body["expression"] == SHORT_TERM_FACTOR_EXPR
    conn = await asyncpg.connect(applied_db)
    try:
        value = await conn.fetchval("SELECT value FROM engine_config WHERE key='factor.custom_expression'")
        assert value is None or json.loads(value) is None
        log = await conn.fetch(
            "SELECT field, old_value, new_value, source FROM config_change_log "
            "WHERE field='factor.custom_expression' ORDER BY id"
        )
        assert [dict(r) for r in log] == [{
            "field": "factor.custom_expression", "old_value": json.dumps(custom),
            "new_value": "null", "source": "manual",
        }]
    finally:
        await conn.close()


async def test_restore_preset_is_idempotent(authed_client, applied_db):
    first = authed_client.post("/api/factor-lab/live-expression/restore-preset", headers=_auth())
    assert first.status_code == 200, first.text
    assert first.json()["changed"] is False
    conn = await asyncpg.connect(applied_db)
    try:
        assert await conn.fetchval("SELECT count(*) FROM config_change_log") == 0
    finally:
        await conn.close()


@pytest.mark.parametrize("sub", [None, "2"])
async def test_restore_preset_requires_admin(authed_client, applied_db, sub):
    await _set_custom_expression(applied_db, "rank(returns)")
    response = authed_client.post(
        "/api/factor-lab/live-expression/restore-preset", headers=_auth(sub) if sub else {},
    )
    assert response.status_code == (403 if sub else 401)
    conn = await asyncpg.connect(applied_db)
    try:
        assert json.loads(await conn.fetchval(
            "SELECT value FROM engine_config WHERE key='factor.custom_expression'")) == "rank(returns)"
    finally:
        await conn.close()
