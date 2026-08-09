"""Refresh-status contract keeps compute and snapshot publication distinct."""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import asyncpg


async def test_last_refresh_exposes_terminal_publish_status(
    client_with_db, applied_db
):
    started = datetime.now(UTC) - timedelta(minutes=2)
    finished = started + timedelta(seconds=5)
    conn = await asyncpg.connect(applied_db)
    try:
        await conn.execute(
            """
            INSERT INTO cron_runs
                (cron_name, started_at, finished_at, ok, error_count, details)
            VALUES ('fast_intraday', $1, $2, true, 0, '{}'::jsonb)
            """,
            started,
            finished,
        )
        await conn.execute(
            """
            INSERT INTO cron_runs
                (cron_name, started_at, finished_at, ok, error_count, details)
            VALUES ('recommendation_publish', $1, $2, true, 0, $3::jsonb)
            """,
            started,
            finished,
            json.dumps(
                {
                    "publish_status": "no_op_same_market_date",
                    "run_id": 38,
                    "market_date": "2026-08-07",
                    "reason": "complete_run_already_exists",
                    "request_id": "refresh-test-1",
                }
            ),
        )
    finally:
        await conn.close()

    body = client_with_db.get("/api/admin/last_refresh").json()
    assert body["fast_intraday"] == started.isoformat()
    assert body["fast_intraday_finished_at"] == finished.isoformat()
    assert body["recommendation_publish"] == {
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "ok": True,
        "status": "no_op_same_market_date",
        "run_id": 38,
        "market_date": "2026-08-07",
        "reason": "complete_run_already_exists",
        "request_id": "refresh-test-1",
    }
