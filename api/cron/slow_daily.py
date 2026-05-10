"""Vercel cron: slow daily signal fetch + partial fusion → DB.

Trigger: 21:30 Asia/Shanghai = 09:30 ET pre-open (cron in vercel.json).
Universe: SP500 ~500 tickers.
Signals: factor, analyst, earnings, insider, macro (5 slow signals).
Output: 1 row per ticker in daily_signals_slow.

Spec §4.1. Always returns 200 with {ok: bool, rows_written, errors}; never
raises 5xx (cron retry storms).
"""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from typing import Any

from alpha_agent.fusion.combine import combine
from alpha_agent.fusion.weights import DEFAULT_WEIGHTS, normalize_weights
from alpha_agent.orchestrator.batch_runner import run_batched
from alpha_agent.signals import analyst, earnings, factor, insider, macro
from alpha_agent.storage.postgres import get_pool
from alpha_agent.storage.queries import insert_signal_slow, log_error

_SLOW_MODULES = {
    "factor": factor,
    "analyst": analyst,
    "earnings": earnings,
    "insider": insider,
    "macro": macro,
}
_SLOW_WEIGHTS = {k: v for k, v in DEFAULT_WEIGHTS.items() if k in _SLOW_MODULES}


async def _fetch_one(ticker: str, as_of: datetime) -> dict:
    return {name: mod.fetch_signal(ticker, as_of) for name, mod in _SLOW_MODULES.items()}


async def handler(limit: int | None = None) -> dict[str, Any]:
    """Vercel function entry point. Always returns a dict (never raises).

    `limit`: cap universe size for diagnostic / Hobby-tier 300s budget.
    None = full SP500 universe (only works under Pro 800s timeout).
    Recommended: 10 for first-time test, 50-80 for daily cron under Hobby.
    """
    from alpha_agent.universe import SP500_UNIVERSE

    pool = await get_pool(os.environ["DATABASE_URL"])
    today = datetime.now(UTC).date().isoformat()
    now = datetime.now(UTC)
    started_at = now
    errors: list[dict] = []

    async def _per_ticker(t: str) -> str:
        sigs = await _fetch_one(t, now)
        norm_w = normalize_weights(_SLOW_WEIGHTS)
        result = combine(sigs, norm_w)
        await insert_signal_slow(
            pool, t, today, result.composite, {"breakdown": result.breakdown}
        )
        return t

    universe = SP500_UNIVERSE[:limit] if limit else SP500_UNIVERSE
    results = await run_batched(universe, _per_ticker, batch_size=20)
    rows_written = sum(1 for v in results.values() if not isinstance(v, Exception))
    for t, v in results.items():
        if isinstance(v, Exception):
            errors.append({"ticker": t, "err": str(v)[:200]})
            await log_error(
                pool,
                layer="cron",
                component="cron.slow_daily",
                ticker=t,
                err_type=type(v).__name__,
                err_message=str(v)[:200],
            )

    finished_at = datetime.now(UTC)
    await pool.execute(
        "INSERT INTO cron_runs "
        "(cron_name, started_at, finished_at, ok, error_count, details) "
        "VALUES ($1, $2, $3, $4, $5, $6::jsonb)",
        "slow_daily",
        started_at,
        finished_at,
        len(errors) == 0,
        len(errors),
        json.dumps({"rows_written": rows_written}),
    )
    return {"ok": True, "rows_written": rows_written, "errors": errors[:5]}
