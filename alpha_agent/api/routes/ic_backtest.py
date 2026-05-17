"""POST /api/cron/ic_backtest_monthly - monthly walk-forward IC backtest.

Invoked by GHA cron on the 1st of each month. Runs all active signals
through 30/60/90d backtest windows, writes results to signal_ic_history
and signal_weight_current. Auto-drops signals whose IC falls below
0.02 by setting their weight = 0; combine.py then ignores them in
composite computation until next month.

No auth (cron-only endpoint; GHA Actions IP can be ratelimited at
Vercel level later if needed).
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter

from alpha_agent.api.dependencies import get_db_pool
from alpha_agent.backtest.ic_engine import run_monthly_ic_backtest

router = APIRouter(prefix="/api/cron", tags=["cron"])


@router.post("/ic_backtest_monthly")
async def ic_backtest_monthly() -> dict[str, Any]:
    pool = await get_db_pool()
    started_at = datetime.now(UTC)
    n = await run_monthly_ic_backtest(pool)
    # Stamp cron_runs (same pattern as other cron handlers).
    await pool.execute(
        """
        INSERT INTO cron_runs (cron_name, started_at, finished_at, ok, error_count, details)
        VALUES ($1, $2, now(), true, 0, $3::jsonb)
        """,
        "ic_backtest_monthly",
        started_at,
        f'{{"signals_updated": {n}}}',
    )
    return {"ok": True, "signals_updated": n}
