import json
import time

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
