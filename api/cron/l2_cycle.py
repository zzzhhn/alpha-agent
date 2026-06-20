"""Cron: advance the L2 paper book one step over the product ledger.

Idempotent + best-effort: registers the canonical strategy, runs the driver
(generate -> fill -> mark for any due rebalance), logs to cron_runs, and ALWAYS
returns a dict (never raises — a cron retry storm must not be possible). Schedule
this daily (GH Actions / vercel cron) so l2_equity_daily accumulates a forward
curve. Errors are surfaced in the response + cron_runs (Silent Exception
Anti-Pattern), never swallowed.
"""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from typing import Any

from alpha_agent.backtest import l2_driver
from alpha_agent.storage.postgres import get_pool


async def handler() -> dict[str, Any]:
    started_at = datetime.now(UTC)
    pool = await get_pool(os.environ["DATABASE_URL"])
    error: str | None = None
    summary: dict[str, Any] = {}
    try:
        strategy_id = await l2_driver.ensure_strategy(pool)
        summary = await l2_driver.run_driver(pool, strategy_id=strategy_id)
    except Exception as exc:  # noqa: BLE001 — never let the cron raise
        error = f"{type(exc).__name__}: {str(exc) or repr(exc)}"[:200]

    await pool.execute(
        "INSERT INTO cron_runs "
        "(cron_name, started_at, finished_at, ok, error_count, details) "
        "VALUES ('l2_cycle', $1, $2, $3, $4, $5::jsonb)",
        started_at, datetime.now(UTC), error is None, 1 if error else 0,
        json.dumps({**summary, "error": error}),
    )
    return {"ok": error is None, **summary, "error": error}
