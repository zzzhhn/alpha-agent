"""Authenticated BRAIN generated-candidate ledger route coverage."""
import time

import asyncpg
import pytest
from jose import jwt

from alpha_agent.brain import store

_SECRET = "test-secret-not-real-0123456789"


def _auth(sub: str = "1") -> dict:
    now = int(time.time())
    token = jwt.encode(
        {"sub": sub, "iat": now, "exp": now + 3600},
        _SECRET,
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def authed_client(client_with_db, monkeypatch):
    monkeypatch.setenv("NEXTAUTH_SECRET", _SECRET)
    return client_with_db


@pytest.mark.asyncio
async def test_run_candidates_requires_owner_and_supports_filters(
    authed_client, applied_db
):
    conn = await asyncpg.connect(applied_db)
    try:
        run_id = await conn.fetchval(
            "INSERT INTO brain_runs (user_id, source, requested_n, generation_target_n) "
            "VALUES (1, 'manual', 1, 1) RETURNING id"
        )
    finally:
        await conn.close()
    pool = await asyncpg.create_pool(applied_db, min_size=1, max_size=1)
    try:
        await store.record_brain_run_candidates(
            pool,
            run_id,
            [{"expression": "rank(close)", "settings": {"decay": 4}}],
        )
    finally:
        await pool.close()

    response = authed_client.get(
        f"/api/brain/runs/{run_id}/candidates?selected=false",
        headers=_auth(),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 1
    assert body["candidates"][0]["expression"] == "rank(close)"

    # TestClient creates a fresh event loop per request; reset the global pool
    # before the second request, matching the existing API test convention.
    import alpha_agent.storage.postgres as _pg
    _pg._pool = None
    _pg._pool_dsn = None
    foreign = authed_client.get(
        f"/api/brain/runs/{run_id}/candidates",
        headers=_auth("2"),
    )
    assert foreign.status_code == 404
