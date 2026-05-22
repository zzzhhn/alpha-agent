"""Tests for human-gated approve/reject/rollback proposal endpoints (Phase 2b)."""
from __future__ import annotations

import json
import time

import asyncpg
import pytest
from jose import jwt

_SECRET = "test-secret-not-real-0123456789"


def _auth(sub: str = "1") -> dict:
    now = int(time.time())
    tok = jwt.encode(
        {"sub": sub, "iat": now, "exp": now + 3600},
        _SECRET,
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture
def authed_client(client_with_db, monkeypatch):
    """client_with_db with NEXTAUTH_SECRET wired so require_user passes."""
    monkeypatch.setenv("NEXTAUTH_SECRET", _SECRET)
    return client_with_db


async def _seed_pending(applied_db):
    conn = await asyncpg.connect(applied_db)
    try:
        return await conn.fetchval(
            "INSERT INTO config_change_log (user_id, field, old_value, new_value, source, status, evidence) "
            "VALUES (0, 'rating.no_trade_band', '0.15', '0.2', 'proposer', 'pending', $1::jsonb) RETURNING id",
            json.dumps({"sharpe_oos": 0.8, "n_trials": 4, "rationale": "band 0.15 to 0.2"}),
        )
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_reject_nonexistent_proposal_404(authed_client, applied_db):
    # No row with this id: reject must 404, not return a misleading ok=true.
    r = authed_client.post("/api/evolution/proposals/999999/reject", headers=_auth())
    assert r.status_code == 404, r.text


@pytest.mark.asyncio
async def test_list_pending_proposals(authed_client, applied_db):
    await _seed_pending(applied_db)
    body = authed_client.get("/api/evolution/proposals").json()
    assert any(p["field"] == "rating.no_trade_band" and p["status"] == "pending" for p in body["proposals"])
    assert body["proposals"][0]["evidence"]["n_trials"] == 4


@pytest.mark.asyncio
async def test_approve_applies_and_marks_approved(authed_client, applied_db):
    pid = await _seed_pending(applied_db)
    r = authed_client.post(f"/api/evolution/proposals/{pid}/approve", headers=_auth())
    assert r.status_code == 200, r.text
    conn = await asyncpg.connect(applied_db)
    try:
        v = await conn.fetchval("SELECT value FROM engine_config WHERE key='rating.no_trade_band'")
        assert json.loads(v) == pytest.approx(0.2)
        st = await conn.fetchval("SELECT status FROM config_change_log WHERE id=$1", pid)
        assert st == "approved"
        n = await conn.fetchval("SELECT count(*) FROM config_change_log WHERE source='approved'")
        assert n >= 1
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_reject_marks_rejected_without_applying(authed_client, applied_db):
    pid = await _seed_pending(applied_db)
    r = authed_client.post(f"/api/evolution/proposals/{pid}/reject", headers=_auth())
    assert r.status_code == 200, r.text
    conn = await asyncpg.connect(applied_db)
    try:
        st = await conn.fetchval("SELECT status FROM config_change_log WHERE id=$1", pid)
        assert st == "rejected"
        exists = await conn.fetchval("SELECT count(*) FROM engine_config WHERE key='rating.no_trade_band'")
        assert exists == 0
    finally:
        await conn.close()


def test_rollback_reverts_applied_change(authed_client, applied_db):
    """Seed -> approve -> rollback; verify engine_config returns to old_value.

    Two sequential TestClient calls are made.  The asyncpg pool singleton is
    bound to the event loop created inside the first request; that loop is
    torn down before the second request starts.  Reset the singleton between
    calls so the second request creates a fresh pool on a fresh loop (mirrors
    the client_with_db fixture teardown pattern).
    """
    import asyncio

    import alpha_agent.storage.postgres as _pg

    pid = asyncio.run(_seed_pending(applied_db))

    # Step 1: approve - pool is created here for the first time.
    r = authed_client.post(f"/api/evolution/proposals/{pid}/approve", headers=_auth())
    assert r.status_code == 200, r.text

    # Reset the singleton so the rollback request creates a fresh pool on a
    # fresh event loop (the previous loop is already closed after step 1).
    _pg._pool = None
    _pg._pool_dsn = None

    # Step 2: rollback - fresh pool, no stale-loop conflict.
    r2 = authed_client.post(f"/api/evolution/proposals/{pid}/rollback", headers=_auth())
    assert r2.status_code == 200, r2.text

    async def _verify(db_url):
        conn = await asyncpg.connect(db_url)
        try:
            v = await conn.fetchval(
                "SELECT value FROM engine_config WHERE key='rating.no_trade_band'"
            )
            rollback_of = await conn.fetchval(
                "SELECT rollback_of FROM config_change_log WHERE source='rollback' ORDER BY id DESC LIMIT 1"
            )
            return json.loads(v), rollback_of
        finally:
            await conn.close()

    val, rollback_of = asyncio.run(_verify(applied_db))
    assert val == pytest.approx(0.15)
    assert rollback_of == pid
