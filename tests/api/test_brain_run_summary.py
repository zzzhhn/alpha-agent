"""Owned BRAIN run aggregates, UTC calendar boundaries and rollout compatibility."""
import time
from datetime import timedelta

import asyncpg
import pytest
from jose import jwt

from alpha_agent.brain import store

_SECRET = "test-secret-not-real-0123456789"


def _auth(user_id: int) -> dict:
    now = int(time.time())
    token = jwt.encode(
        {"sub": str(user_id), "iat": now, "exp": now + 3600},
        _SECRET,
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def authed_client(client_with_db, monkeypatch):
    monkeypatch.setenv("NEXTAUTH_SECRET", _SECRET)
    return client_with_db


@pytest.mark.asyncio
@pytest.mark.parametrize("user_id", [1, 2])
async def test_brain_summary_isolates_users_and_all_counters(
    authed_client, applied_db, user_id
):
    conn = await asyncpg.connect(applied_db)
    try:
        for owner in (1, 2):
            for status in ("queued", "running", "completed", "failed"):
                await conn.execute(
                    "INSERT INTO brain_runs (user_id, source, status, generated_n, "
                    "simulated_n, passed_n, flagged_n, rejected_n, sim_error_n) "
                    "VALUES ($1, 'manual', $2, $3, $3, $3, $3, $3, $3)",
                    owner, status, owner,
                )
        bounds = await conn.fetchrow(
            "SELECT min(created_at) AS first, max(created_at) AS last "
            "FROM brain_runs WHERE user_id=$1", user_id,
        )
    finally:
        await conn.close()
    response = authed_client.get("/api/brain/runs/summary", headers=_auth(user_id))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total_runs"] == 4
    assert body["by_status"] == dict.fromkeys(
        ("queued", "running", "completed", "failed"), 1
    )
    assert body["totals"] == dict.fromkeys(
        ("generated", "simulated", "passed", "flagged", "rejected", "sim_error"),
        user_id * 4,
    )
    assert body["first_run_at"] == bounds["first"].isoformat()
    assert body["last_run_at"] == bounds["last"].isoformat()
    assert len(body["last_30d"]) == 1
    assert body["last_30d"][0]["runs"] == 4
    for key in ("passed", "flagged", "rejected", "sim_error"):
        assert body["last_30d"][0][key] == user_id * 4


def test_brain_summary_empty(authed_client):
    response = authed_client.get("/api/brain/runs/summary", headers=_auth(1))
    assert response.status_code == 200
    assert response.json() == {
        "total_runs": 0,
        "by_status": dict.fromkeys(("queued", "running", "completed", "failed"), 0),
        "totals": dict.fromkeys(
            ("generated", "simulated", "passed", "flagged", "rejected", "sim_error"), 0
        ),
        "last_30d": [], "first_run_at": None, "last_run_at": None,
    }


@pytest.mark.asyncio
async def test_brain_summary_utc_30_day_window(applied_db):
    # A non-UTC DB session must not move the date or exclude midnight UTC.
    pool = await asyncpg.create_pool(
        applied_db, min_size=1, max_size=1,
        server_settings={"timezone": "America/Los_Angeles"},
    )
    try:
        today = await pool.fetchval("SELECT (now() AT TIME ZONE 'UTC')::date")
        for day_offset, seconds in ((-30, 86399), (-29, 0), (-1, 86399), (0, 0), (1, 0)):
            await pool.execute(
                "INSERT INTO brain_runs (user_id, source, status, created_at, "
                "passed_n, flagged_n, rejected_n, sim_error_n) "
                "VALUES (1, 'manual', 'completed', "
                "(($1::date + $2::int)::timestamp AT TIME ZONE 'UTC') "
                "+ $3::int * interval '1 second', 1, 2, 3, 4)",
                today, day_offset, seconds,
            )
        summary = await store.summarize_brain_runs(pool, 1)
        assert summary["total_runs"] == 5
        assert summary["last_30d"] == [
            {"date": (today + timedelta(days=offset)).isoformat(), "runs": 1,
             "passed": 1, "flagged": 2, "rejected": 3, "sim_error": 4}
            for offset in (-29, -1, 0)
        ]
    finally:
        await pool.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ["table", "column"])
async def test_brain_summary_missing_migration(authed_client, applied_db, missing):
    conn = await asyncpg.connect(applied_db)
    try:
        if missing == "table":
            await conn.execute("DROP TABLE brain_runs CASCADE")
        else:
            await conn.execute("ALTER TABLE brain_runs DROP COLUMN generated_n")
    finally:
        await conn.close()
    response = authed_client.get("/api/brain/runs/summary", headers=_auth(1))
    assert response.status_code == 200, response.text
    assert response.json()["total_runs"] == 0
    assert response.json()["last_30d"] == []


def test_brain_summary_unauthenticated(authed_client):
    assert authed_client.get("/api/brain/runs/summary").status_code == 401
