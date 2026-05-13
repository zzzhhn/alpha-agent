"""Vercel cron: fast intraday signal fetch + full fusion + alert emission.

Trigger: every 15min, weekdays 9:30-16:00 ET.
Universe: watchlist ∪ top_100 from daily_signals_slow.
Signals: full 10 (technicals, options, news, premarket fresh; factor/analyst/
earnings/insider/macro pulled from cached slow row + recombined).

Spec §4.1, §4.3. Always returns 200 with {ok, rows_written, errors}; never
raises 5xx.
"""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from typing import Any

from alpha_agent.fusion.combine import combine
from alpha_agent.fusion.rating import compute_confidence, map_to_tier
from alpha_agent.fusion.weights import DEFAULT_WEIGHTS
from alpha_agent.orchestrator.alert_detector import detect_alerts
from alpha_agent.orchestrator.batch_runner import run_batched
from alpha_agent.signals import (
    analyst,
    calendar as cal,
    earnings,
    factor,
    insider,
    macro,
    news,
    options,
    premarket,
    technicals,
)
from alpha_agent.storage.postgres import get_pool
from alpha_agent.storage.queries import enqueue_alert, log_error, upsert_signal_fast

_ALL_MODULES = {
    "factor": factor,
    "technicals": technicals,
    "analyst": analyst,
    "earnings": earnings,
    "news": news,
    "insider": insider,
    "options": options,
    "premarket": premarket,
    "macro": macro,
    "calendar": cal,
}


async def handler(
    limit: int | None = None, offset: int | None = None
) -> dict[str, Any]:
    """Vercel function entry point. Always returns a dict (never raises).

    `limit`: cap watchlist size for diagnostic / Hobby-tier 300s budget.
        None = full watchlist (top_n=100). Recommended: 10 for first test,
        75 for GH Actions multi-shot (3.8s/ticker × 75 ≈ 285s, fits Hobby).
    `offset`: start index into the watchlist. Enables multi-shot coverage:
        3 shots of (limit=75, offset=0/75/150) covers top 225 tickers per cycle.
    """
    from alpha_agent.universe import get_watchlist

    pool = await get_pool(os.environ["DATABASE_URL"])
    now = datetime.now(UTC)
    today = now.date().isoformat()
    started_at = now
    errors: list[dict] = []
    bucket = int(now.timestamp()) // 1800  # 30-min dedup window

    universe = get_watchlist(top_n=limit if limit else 100, offset=offset or 0)

    async def _per_ticker(t: str) -> str:
        # Fetch all 10 signals
        sigs = {name: mod.fetch_signal(t, now) for name, mod in _ALL_MODULES.items()}

        # Combine + rate
        result = combine(sigs, DEFAULT_WEIGHTS)
        contributing_zs = [
            b["z"] for b in result.breakdown if b["weight_effective"] > 0
        ]
        confidence = compute_confidence(contributing_zs)
        rating = map_to_tier(result.composite)

        # Read previous card for rating_change comparison
        prev_row = await pool.fetchrow(
            "SELECT rating, composite, breakdown FROM daily_signals_fast "
            "WHERE ticker=$1 AND date=$2::text::date",
            t,
            today,
        )
        prev_card: dict | None = None
        if prev_row is not None:
            raw_bd = prev_row["breakdown"]
            bd_data = (
                json.loads(raw_bd) if isinstance(raw_bd, str) else raw_bd or {}
            )
            prev_card = {
                "ticker": t,
                "rating": prev_row["rating"],
                "composite_score": prev_row["composite"],
                "breakdown": bd_data.get("breakdown", []),
            }
        curr_card = {
            "ticker": t,
            "rating": rating,
            "composite_score": result.composite,
            "breakdown": result.breakdown,
        }

        # Write fast row
        await upsert_signal_fast(
            pool,
            t,
            today,
            result.composite,
            rating,
            confidence,
            {"breakdown": result.breakdown},
            partial=False,
        )

        # Detect + enqueue alerts
        for alert in detect_alerts(prev_card, curr_card):
            await enqueue_alert(pool, t, alert["type"], alert["payload"], bucket)

        return t

    results = await run_batched(universe, _per_ticker, batch_size=20)
    rows_written = sum(1 for v in results.values() if not isinstance(v, Exception))
    for t, v in results.items():
        if isinstance(v, Exception):
            errors.append({"ticker": t, "err": str(v)[:200]})
            await log_error(
                pool,
                layer="cron",
                component="cron.fast_intraday",
                ticker=t,
                err_type=type(v).__name__,
                err_message=str(v)[:200],
            )

    await pool.execute(
        "INSERT INTO cron_runs "
        "(cron_name, started_at, finished_at, ok, error_count, details) "
        "VALUES ($1, $2, $3, $4, $5, $6::jsonb)",
        "fast_intraday",
        started_at,
        datetime.now(UTC),
        len(errors) == 0,
        len(errors),
        json.dumps({"rows_written": rows_written}),
    )
    return {"ok": True, "rows_written": rows_written, "errors": errors[:5]}
