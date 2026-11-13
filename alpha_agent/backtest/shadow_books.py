"""Frozen forward-only paper comparators; never publication or bot accounts."""
from __future__ import annotations

import json
import math
from datetime import date, datetime, timedelta
from functools import lru_cache
from statistics import mean, pstdev

from alpha_agent.backtest.l2 import DEFAULT_PARAMS, select_holdings
from alpha_agent.backtest.l2_continuous import INITIAL_CASH
from alpha_agent.data.security_identity import valid_research_symbol
from alpha_agent.market_session import xnys_sessions

SPLICE_END = date(2026, 10, 30)
SHADOW_RULES = {
    "shadow_factor_12_1": "factor_12_1",
    "shadow_band_40_80": "band_40_80",
    "shadow_bot_rule_weekly": "bot_rule_weekly",
}
RULE_SUMMARIES = {
    "factor_12_1": "Replace only the effective factor contribution with z(close[D-21]/close[D-252]-1); top50, 2%, 5 sessions, 10bps",
    "band_40_80": "Keep eligible holdings rank<=80; buy rank<=40; max50, 2%, 5 sessions, 10bps",
    "bot_rule_weekly": "Rule comparator, no LLM: first complete snapshot per ISO week, rank top8, equal weight capped25%, 15bps daily-close approximation",
}


def protocol_name(name: str) -> str:
    return f"shadow-{name}-v0.1-20261113"


async def ensure_shadow_book(pool, *, name: str) -> int:
    """Register rules and activation boundary atomically; never rewrite either."""
    rule = SHADOW_RULES[name]
    params = {
        **DEFAULT_PARAMS, "accounting": "continuous_share_delta", "sleeve": "tactical",
        "shadow": True, "changes_one_factor_vs": "canonical_top50_continuous v3",
        "rule": rule, "rule_summary": RULE_SUMMARIES[rule],
        "preregistered": "2026-11-13", "protocol": protocol_name(name),
        "promotion": "requires user approval + new quant-p0 protocol version; never spliced",
        "rebalance_days": 5, "initial_cash": INITIAL_CASH,
        "minimum_sessions": 60,
    }
    if rule == "factor_12_1":
        params["price_history"] = "253 complete XNYS sessions live; otherwise bundled v3 <=2026-10-30 + live >2026-10-30; reject >45% moves; no rescaling"
        params["normalization"] = "eligible valid snapshot universe; population std; clip [-3,3]"
    if rule == "bot_rule_weekly":
        params.update(top_n=8, max_position=0.25, cost_bps=15.0,
                      rebalance="iso_week_first_snapshot")
    async with pool.acquire() as conn, conn.transaction():
        sid = await conn.fetchval(
            "INSERT INTO l2_strategy(name,version,params_json) VALUES($1,1,$2::jsonb) "
            "ON CONFLICT(name,version) DO NOTHING RETURNING id", name, json.dumps(params))
        if sid is None:
            sid = await conn.fetchval("SELECT id FROM l2_strategy WHERE name=$1 AND version=1", name)
        await conn.execute(
            "INSERT INTO l2_account(strategy_id,initial_cash,cash,nav,start_after_run_id) "
            "SELECT $1,$2,$2,$2,COALESCE(max(id),0) FROM research_run WHERE status='complete' "
            "ON CONFLICT(strategy_id) DO NOTHING", sid, INITIAL_CASH)
    return int(sid)


def _eligible(snapshots):
    return [dict(s) for s in snapshots if s["eligible"] and valid_research_symbol(s["ticker"])]


def band_holdings(snapshots, held: set[str]) -> list[dict]:
    ranked = sorted((s for s in _eligible(snapshots) if s["rank"] is not None
                     and 1 <= s["rank"] <= 80), key=lambda s: (s["rank"], s["ticker"]))
    chosen = [s for s in ranked if s["ticker"] in held][:50]
    chosen += [s for s in ranked if s["ticker"] not in held and s["rank"] <= 40][:50-len(chosen)]
    return [{"ticker": s["ticker"], "rank": s["rank"], "tier": s["tier"], "target_weight": 0.02}
            for s in chosen]


def bot_holdings(snapshots) -> list[dict]:
    chosen = sorted((s for s in _eligible(snapshots) if s["rank"] is not None
                     and s["rank"] > 0), key=lambda s: (s["rank"], s["ticker"]))[:8]
    weight = min(1 / len(chosen), 0.25) if chosen else 0
    return [{"ticker": s["ticker"], "rank": s["rank"], "tier": s["tier"], "target_weight": weight}
            for s in chosen]


@lru_cache(maxsize=1)
def research_closes() -> dict[str, dict[date, float]]:
    # Reuse the bundled loader without mutating its path, cache or live panel.
    from alpha_agent.factor_engine.factor_backtest import PARQUET_PATH, PARQUET_V3_PATH, _load_panel
    if PARQUET_PATH != PARQUET_V3_PATH:
        raise ValueError("shadow momentum requires the bundled v3 parquet")
    panel = _load_panel()
    dates = [date.fromisoformat(str(d)[:10]) for d in panel.dates]
    return {t: {d: float(panel.close[i, j]) for i, d in enumerate(dates) if d <= SPLICE_END}
            for j, t in enumerate(panel.tickers)}


def momentum_value(sessions: list[date], live: dict, research: dict) -> tuple[float | None, str]:
    """close[D-21]/close[D-252]-1; no forward fills, rescaling or seam repair.

    12-1 momentum only reads two closes (D-252 and D-21); the bars in between
    are used solely to reject unadjusted splits and feed errors. Sessions on
    or before the research cut-off come from the bundled panel when the live
    table has no row (it starts 2026-02-23 and misses some days, e.g.
    2026-07-24); later sessions must come from the live table.
    """
    if len(sessions) != 253:
        return None, "insufficient_history"
    needed = sessions[:-21]  # D-252 .. D-21; D-20..D are not read by 12-1
    spliced = not all(live.get(d) is not None for d in needed)
    values = []
    for d in needed:
        value = live.get(d)
        if value is None and d <= SPLICE_END:
            value = research.get(d)
        values.append(value)
    if any(v is None or not math.isfinite(v) or v <= 0 for v in values):
        return None, "insufficient_history"
    if any(abs(b/a - 1) > 0.45 for a, b in zip(values, values[1:])):
        return None, "suspect_jump"
    return values[-1] / values[0] - 1, "spliced" if spliced else "live"


def _json(value):
    return json.loads(value) if isinstance(value, str) else (value or {})


def substitute_composite(score: float, breakdown, z_mom: float, coverage=None) -> float | None:
    """Swap only the factor term of the emitted composite.

    The fast composite is sum(z * weight_effective) * sqrt(coverage)
    (alpha_agent/fusion/combine.py), so the factor term is removed and
    replaced with the same weight and the same coverage damping.
    """
    entries = _json(breakdown)
    if isinstance(entries, dict):
        coverage = entries.get("coverage", coverage)
        entries = entries.get("breakdown", [])
    try:
        damp = math.sqrt(float(coverage)) if coverage is not None else 1.0
    except (TypeError, ValueError):
        return None
    if not math.isfinite(damp) or damp < 0:
        return None
    for entry in entries:
        if entry.get("signal") == "factor":
            try:
                z, w = float(entry["z"]), float(entry["weight_effective"])
                result = float(score) + (w * z_mom - w * z) * damp
                return result if all(math.isfinite(v) for v in (z, w, result)) else None
            except (KeyError, TypeError, ValueError):
                return None
    return None


async def factor_holdings(pool, *, snapshots, run_id: int, signal_date: date, info: dict) -> list[dict]:
    eligible = _eligible(snapshots)
    sessions = xnys_sessions(signal_date - timedelta(days=500), signal_date)[-253:]
    tickers = [s["ticker"] for s in eligible]
    rows = await pool.fetch(
        "SELECT ticker,date,close FROM daily_prices WHERE ticker=ANY($1::text[]) AND date BETWEEN $2 AND $3",
        tickers, sessions[0], signal_date)
    live = {t: {} for t in tickers}
    for row in rows:
        live[row["ticker"]][row["date"]] = float(row["close"]) if row["close"] is not None else None
    need_research = any(not all(d in live[t] for d in sessions) for t in tickers)
    research = research_closes() if need_research else {}
    momentum = {}
    info.update(eligible=len(eligible), insufficient_history=0, suspect_jump=0,
                missing_breakdown=0, spliced=0, live=0, fallback_breakdown=0)
    for t in tickers:
        value, reason = momentum_value(sessions, live[t], research.get(t, {}))
        info[reason] += 1
        if value is not None:
            momentum[t] = value
    mu = mean(momentum.values()) if momentum else 0
    sigma = pstdev(momentum.values()) if momentum else 0
    # The immutable payload carries no breakdown. Its as_of is the fetched_at
    # of the exact daily_signals_fast row it was built from (fast rows are
    # keyed by the UTC date, not the market date), so join on that instant.
    as_of = {s["ticker"]: _json(s["user_visible_payload_json"]).get("as_of") for s in eligible}
    fallback_rows = await pool.fetch(
        "SELECT f.ticker, f.fetched_at, f.breakdown FROM daily_signals_fast f "
        "JOIN research_run r ON r.id=$1 "
        "WHERE f.ticker=ANY($2::text[]) AND f.fetched_at<=r.created_at "
        "AND f.date BETWEEN $3 AND $3 + 4",
        run_id, tickers, signal_date)
    fallback = {}
    for row in fallback_rows:
        stamp = as_of.get(row["ticker"])
        if stamp and row["fetched_at"].isoformat() == datetime.fromisoformat(stamp).isoformat():
            fallback[row["ticker"]] = _json(row["breakdown"])
    projected = []
    for s in eligible:
        t = s["ticker"]
        payload = _json(s["user_visible_payload_json"])
        breakdown = payload.get("breakdown")
        if not breakdown:
            breakdown = fallback.get(t, {})
            if breakdown:
                info["fallback_breakdown"] += 1
        # Snapshot composite is the frozen emitted score, never fast composite.
        score = payload.get("composite_score", s.get("composite_z"))
        z = max(-3, min(3, (momentum[t]-mu)/sigma)) if t in momentum and sigma else 0
        composite = substitute_composite(score, breakdown, z,
                                         coverage=(fallback.get(t) or {}).get("coverage"))
        if composite is None:
            info["missing_breakdown"] += 1
        if t in momentum and composite is not None:
            projected.append({**s, "shadow_composite": composite})
    projected.sort(key=lambda s: (-s["shadow_composite"], s["ticker"]))
    # The live selector prefers BUY/OW tiers, and a tier is a function of the
    # composite. Re-derive it from the shadow composite with the same unbanded
    # thresholds, so the old factor cannot leak in through the tier.
    from alpha_agent.fusion.rating import map_to_tier
    for rank, s in enumerate(projected, 1):
        s["rank"] = rank
        s["tier"] = map_to_tier(s["shadow_composite"])
    info["selected_universe"] = len(projected)
    info["excluded"] = len(eligible) - len(projected)
    return select_holdings(projected, top_n=50, max_position=0.02)


async def select_shadow_holdings(pool, *, rule, snapshots, positions, run_id, signal_date, info):
    if rule == "band_40_80":
        return band_holdings(snapshots, {p["ticker"] for p in positions})
    if rule == "bot_rule_weekly":
        return bot_holdings(snapshots)
    if rule == "factor_12_1":
        return await factor_holdings(pool, snapshots=snapshots, run_id=run_id,
                                     signal_date=signal_date, info=info)
    raise ValueError(f"unknown shadow rule: {rule}")
