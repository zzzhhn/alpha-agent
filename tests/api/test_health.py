"""Tests for /api/_health{,/signals,/cron}."""
from __future__ import annotations

from datetime import UTC, datetime

import asyncpg


async def test_health_returns_json_content_type(client_with_db):
    r = client_with_db.get("/api/_health")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")


async def test_health_includes_db_status(client_with_db):
    r = client_with_db.get("/api/_health")
    body = r.json()
    assert body["db"] == "ok"


async def test_health_signals_returns_all_rows(client_with_db, applied_db):
    """Every signal listed even with no error_log entries (last_error=null).

    The monitored set is now derived from the single signal registry, so it
    covers ALL live signals. Previously a hand-kept list that had drifted
    (missing geopolitical_impact + supply_chain); deriving it closes that gap.
    """
    from alpha_agent.signals.registry import all_signal_names

    r = client_with_db.get("/api/_health/signals")
    assert r.status_code == 200
    sigs = r.json()["signals"]
    names = {s["name"] for s in sigs}
    assert names == set(all_signal_names())
    assert {"geopolitical_impact", "supply_chain"} <= names  # the closed drift gap


async def test_health_cron_returns_recent_runs_per_cron(client_with_db, applied_db):
    """Seed 3 slow_daily runs; expect them in /api/_health/cron."""
    conn = await asyncpg.connect(applied_db)
    try:
        for _ in range(3):
            await conn.execute(
                "INSERT INTO cron_runs "
                "(cron_name, started_at, finished_at, ok, error_count) "
                "VALUES ($1, $2, $3, $4, $5)",
                "slow_daily",
                datetime.now(UTC),
                datetime.now(UTC),
                True,
                0,
            )
    finally:
        await conn.close()

    r = client_with_db.get("/api/_health/cron")
    assert r.status_code == 200
    cron_runs = r.json()["cron"]
    assert len(cron_runs.get("slow_daily", [])) == 3
