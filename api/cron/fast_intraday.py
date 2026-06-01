"""Vercel cron: fast intraday signal fetch + full fusion + alert emission.

Tiered design (2026-05-16): one entry point, a `tier` query param selects
which subset of the 10 signal modules to refresh. Other signals are reused
from the previous breakdown stored in daily_signals_fast and re-combined
into a fresh composite. This lets the GH Actions workflow run technicals
every 15min for all 557 tickers without re-fetching options/news/insider
at that cadence (Yahoo IP-rate-limit + GHA minutes both punish us).

Tiers:
  full  - all 10 signals (legacy; the periodic bootstrap every 2h)
  tech  - technicals only (every 15min during market)
  mid   - options + analyst + premarket (every hour)
  slow  - news + insider (every 4h)

Bootstrap: any tier finding a ticker with no row today falls back to a
full 10-module fetch so the first run of the day always populates every
signal slot, regardless of which tier fires first.

Race note: two tier runs that overlap on the same ticker can lose one
update (last writer wins). Mitigations: schedules are staggered (tech at
:00,:15,:30,:45; mid at :05; slow at :10) so overlaps are rare, and each
tier rewrites the same row on the next run, so the system self-heals.

Always returns 200 with {ok, tier, rows_written, errors}; never raises 5xx.
Spec §4.1, §4.3.
"""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from typing import Any

from alpha_agent.fusion.combine import combine
from alpha_agent.fusion.rating import (
    compute_confidence, map_to_tier, map_to_tier_with_band,
)
from alpha_agent.fusion.weights import DEFAULT_WEIGHTS
from alpha_agent.orchestrator.alert_detector import detect_alerts
from alpha_agent.orchestrator.batch_runner import run_batched
from alpha_agent.signals import (
    analyst,
    calendar as cal,
    earnings,
    factor,
    geopolitical_impact,
    insider,
    macro,
    news,
    options,
    political_impact,
    premarket,
    technicals,
)
from alpha_agent.signals.base import SignalScore
from alpha_agent.config_store import refresh_config
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
    "political_impact": political_impact,
    "geopolitical_impact": geopolitical_impact,
}

# Tier -> the signal modules that tier refreshes this run.
_TIERS: dict[str, list[str]] = {
    "full": list(_ALL_MODULES.keys()),
    "tech": ["technicals"],
    "mid":  ["options", "analyst", "premarket"],
    "slow": ["news", "insider"],
}


def _sig_from_breakdown(entry: dict, ticker: str) -> SignalScore:
    """Reconstruct a SignalScore from a previously-stored breakdown entry.

    Used by tier runs to seed the sigs dict with cached values that
    combine() can re-evaluate against the freshly-fetched tier subset.
    confidence is read directly from the entry; pre-existing rows written
    before combine.py started persisting confidence fall back to a binary
    "kept it last time -> 1.0, dropped it -> 0.0" derived from
    weight_effective.
    """
    conf = entry.get("confidence")
    if conf is None:
        conf = 1.0 if (entry.get("weight_effective") or 0) > 0 else 0.0
    ts_raw = entry.get("timestamp")
    try:
        as_of = datetime.fromisoformat(ts_raw) if ts_raw else datetime.now(UTC)
    except (TypeError, ValueError):
        as_of = datetime.now(UTC)
    return {
        "ticker": ticker,
        "z": entry.get("z"),
        "raw": entry.get("raw"),
        "confidence": conf,
        "as_of": as_of,
        "source": entry.get("source") or "cache",
        "error": entry.get("error"),
    }


def _parse_breakdown(raw: Any) -> list[dict]:
    if raw is None:
        return []
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        return data.get("breakdown", []) if isinstance(data, dict) else []
    except (TypeError, json.JSONDecodeError):
        return []


async def handler(
    limit: int | None = None,
    offset: int | None = None,
    tier: str = "full",
) -> dict[str, Any]:
    """Vercel function entry point. Always returns a dict (never raises).

    `tier`: one of full / tech / mid / slow; controls which signal modules
        get refreshed. Other modules' values are pulled from the cached
        breakdown and re-combined.
    `limit`: cap universe slice per shard. None defaults to 100; the GH
        Actions workflow passes larger values per tier to fit the budget.
    `offset`: start index into the universe. Enables multi-shot coverage.
    """
    if tier not in _TIERS:
        return {"ok": False, "tier": tier, "error": f"unknown tier: {tier}"}
    tier_modules = _TIERS[tier]

    from alpha_agent.universe import get_watchlist

    pool = await get_pool(os.environ["DATABASE_URL"])
    await refresh_config(pool)
    # Prime insider from the precomputed Form 4 table (SEC fetch lives in a
    # separate job). Harmless when this tier reuses insider from the prior
    # breakdown; needed when the "slow" tier refreshes news + insider.
    from alpha_agent.storage.queries import load_all_insider_form4
    insider.prime_cache(await load_all_insider_form4(pool))
    now = datetime.now(UTC)
    today = now.date().isoformat()
    started_at = now
    errors: list[dict] = []
    bucket = int(now.timestamp()) // 1800

    base_universe = get_watchlist(top_n=limit if limit else 100, offset=offset or 0)
    # offset=0 shard unions in every user's watchlist tickers so a starred
    # ticker gets intraday coverage even when not in the SP500 head.
    if (offset or 0) == 0:
        wl_rows = await pool.fetch("SELECT DISTINCT ticker FROM user_watchlist")
        extras = {r["ticker"] for r in wl_rows} - set(base_universe)
        universe = base_universe + sorted(extras)
    else:
        universe = base_universe

    # Phase 2 dual-factor: compute LONG_TERM mode universe-wide ONCE per
    # shard (panel load + cross-section eval are universe-level operations,
    # not per-ticker). The SHORT mode value flows through normally as
    # factor.z; we patch z_long into breakdown.raw post-combine so the
    # picks lean endpoint can offer a ?mode=long re-rank without recomputing.
    # Best-effort: if long eval fails, z_long stays absent and the UI
    # gracefully falls back to single-mode display.
    long_factor_scores: dict[str, float] = {}
    if "factor" in tier_modules:
        try:
            from alpha_agent.signals.factor import (
                LONG_TERM_FACTOR_EXPR, _evaluate_for_universe,
            )
            long_factor_scores = _evaluate_for_universe(
                now, expr=LONG_TERM_FACTOR_EXPR,
            )
        except Exception as exc:
            errors.append({
                "ticker": "_UNIVERSE_",
                "err": f"long_factor_eval_failed: {type(exc).__name__}: {exc}"[:200],
            })

    async def _per_ticker(t: str) -> str:
        # Fetch fresh signals for this tier first (slow IO, no DB held).
        # Modules expose either sync fetch_signal or async afetch_signal;
        # async-native ones (news, political_impact - query asyncpg pool
        # directly) MUST be awaited, not asyncio.run'd, because we're
        # already inside a running loop here. See feedback memory
        # feedback_asyncio_run_in_async_context.md.
        fresh: dict[str, SignalScore] = {}
        for name in tier_modules:
            mod = _ALL_MODULES[name]
            afetch = getattr(mod, "afetch_signal", None)
            if afetch is not None:
                fresh[name] = await afetch(t, now)
            else:
                fresh[name] = mod.fetch_signal(t, now)

        # Read the existing row to drive bootstrap detection + alert diff.
        prev_row = await pool.fetchrow(
            "SELECT rating, composite, breakdown FROM daily_signals_fast "
            "WHERE ticker=$1 AND date=$2::text::date",
            t, today,
        )
        prev_bd = _parse_breakdown(prev_row["breakdown"]) if prev_row else []

        # Bootstrap: a tier run on a ticker with no row today fetches the
        # missing modules now so the first row of the day always has all
        # 10 signals populated. Costs an extra ~3s but only on first hit.
        if tier != "full" and prev_row is None:
            missing = [n for n in _ALL_MODULES if n not in fresh]
            for name in missing:
                mod = _ALL_MODULES[name]
                afetch = getattr(mod, "afetch_signal", None)
                if afetch is not None:
                    fresh[name] = await afetch(t, now)
                else:
                    fresh[name] = mod.fetch_signal(t, now)

        # Build the sigs dict combine() will see: fresh values for the
        # tier (or all 10 on bootstrap / full), cached values for the rest.
        if tier == "full" or prev_row is None:
            sigs: dict[str, SignalScore] = dict(fresh)
        else:
            sigs = {
                e["signal"]: _sig_from_breakdown(e, t)
                for e in prev_bd
                if e.get("signal") in _ALL_MODULES
            }
            sigs.update(fresh)

        # Combine + rate
        result = combine(sigs, DEFAULT_WEIGHTS)
        contributing_zs = [
            b["z"] for b in result.breakdown if b["weight_effective"] > 0
        ]
        confidence = compute_confidence(contributing_zs)
        # B2 (2026-05-19): hysteresis band over yesterday's tier to suppress
        # threshold-adjacent wobble. raw_tier = legacy unbanded mapping;
        # rating = sticky tier the user actually sees. tier_flip_today
        # flags rows where the band saved a flip (transparency for the UI).
        raw_tier = map_to_tier(result.composite)
        prev_rating = prev_row["rating"] if prev_row is not None else None
        rating = map_to_tier_with_band(result.composite, prev_rating)
        tier_flip_today = bool(raw_tier != rating)

        # Prev card for alert diff
        prev_card: dict | None = None
        if prev_row is not None:
            prev_card = {
                "ticker": t,
                "rating": prev_row["rating"],
                "composite_score": prev_row["composite"],
                "breakdown": prev_bd,
            }
        curr_card = {
            "ticker": t,
            "rating": rating,
            "composite_score": result.composite,
            "breakdown": result.breakdown,
        }

        # Phase 2 dual-factor patch: attach z_long to factor breakdown raw so
        # picks lean endpoint can re-rank on mode=long without recompute.
        if t in long_factor_scores:
            for bd_entry in result.breakdown:
                if bd_entry.get("signal") == "factor":
                    raw = bd_entry.get("raw")
                    if isinstance(raw, dict):
                        raw["z_long"] = float(long_factor_scores[t])
                        # Also stash z_short = current z explicitly for clarity;
                        # frontend can read either without inferring active mode.
                        raw["z_short"] = float(bd_entry.get("z") or 0.0)
                    break

        # B5 (2026-05-19): GEX intraday regime as conditioning variable.
        # Computed inline rather than via _ALL_MODULES because regime is
        # a "this is a buy-dip day vs a trend day" classifier surfaced
        # alongside the signals, not a contributing alpha signal that
        # combine() should weight. None on chain fetch / NaN failure.
        gex_info: dict | None = None
        if tier == "full":
            try:
                from alpha_agent.signals.gex import compute_gex as _gex
                gex_info = _gex(t, now)
            except Exception as exc:  # noqa: BLE001 — yfinance raises arbitrary types
                # GEX failure must not break the rest of the cron cycle.
                # Logged silently here; the next tick re-tries.
                from alpha_agent.signals.gex import logger as _gex_logger
                _gex_logger.warning(
                    "gex outer failure ticker=%s: %s: %s",
                    t, type(exc).__name__, exc,
                )

        await upsert_signal_fast(
            pool, t, today, result.composite, rating, confidence,
            {
                "breakdown": result.breakdown,
                "tier_flip_today": tier_flip_today,
                "raw_tier": raw_tier,
                "gex_info": gex_info,
            },
            partial=False,
        )

        for alert in detect_alerts(prev_card, curr_card):
            await enqueue_alert(pool, t, alert["type"], alert["payload"], bucket)

        return t

    results = await run_batched(universe, _per_ticker, batch_size=20)
    rows_written = sum(1 for v in results.values() if not isinstance(v, Exception))
    for t, v in results.items():
        if isinstance(v, Exception):
            err_msg = f"{type(v).__name__}: {str(v) or repr(v)}"[:200]
            errors.append({"ticker": t, "err": err_msg})
            await log_error(
                pool,
                layer="cron",
                component=f"cron.fast_intraday[{tier}]",
                ticker=t,
                err_type=type(v).__name__,
                err_message=str(v) or repr(v),
            )

    # Distinct cron_name per tier so each tier has its own history in
    # cron_runs. tier="full" keeps the legacy "fast_intraday" name for
    # backward compat with /api/admin/last_refresh + the picks
    # RefreshButton (which polls last_refresh.fast_intraday).
    cron_name = "fast_intraday" if tier == "full" else f"fast_{tier}"
    await pool.execute(
        "INSERT INTO cron_runs "
        "(cron_name, started_at, finished_at, ok, error_count, details) "
        "VALUES ($1, $2, $3, $4, $5, $6::jsonb)",
        cron_name, started_at, datetime.now(UTC),
        len(errors) == 0, len(errors),
        json.dumps({"rows_written": rows_written, "tier": tier}),
    )
    return {
        "ok": True, "tier": tier,
        "rows_written": rows_written, "errors": errors[:5],
    }
