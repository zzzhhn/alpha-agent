"""Shared single-ticker signal lookup: daily_signals_fast preferred,
daily_signals_slow as fallback.

picks_lean unions the two tables for the *list*; this is the single-ticker
equivalent for the stock-detail and brief endpoints. Without it, any route
that reads daily_signals_fast by ticker 404s for a slow-only ticker (one
the daily pipeline covered but the ~240-ticker intraday cron did not), e.g.
NVDA - which is exactly what made /stock/NVDA throw a server exception.

The slow table stores only composite_partial + breakdown, so for a
slow-only row rating is derived via map_to_tier and confidence via
compute_confidence from the breakdown z's, the same way the fast cron does.
"""
from __future__ import annotations

import json
import math

import asyncpg

from alpha_agent.backtest.confidence_calibration import apply_calibration
from alpha_agent.fusion.rating import calibrated_confidence, map_to_tier


def _safe_float(v: object, default: float = 0.0) -> float:
    """NaN/Inf/None -> default. PG DOUBLE PRECISION can hold NaN and both
    map_to_tier and Pydantic/JSON serialization choke on it."""
    if v is None:
        return default
    try:
        f = float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return default if (math.isnan(f) or math.isinf(f)) else f


def _parse_breakdown(raw: object) -> list[dict]:
    """The breakdown JSONB comes back from asyncpg as a str; tolerate None
    and malformed JSON by degrading to an empty list."""
    try:
        return json.loads(raw).get("breakdown", [])  # type: ignore[arg-type]
    except (TypeError, json.JSONDecodeError, AttributeError):
        return []


def _parse_tier_flip(raw) -> bool:
    """Pull the B2 hysteresis-band tier_flip_today flag out of the wrapped
    breakdown JSON. False for slow-only rows (no band logic runs there)
    and any row predating the B2 ship.
    """
    try:
        return bool(json.loads(raw).get("tier_flip_today", False))  # type: ignore[arg-type]
    except (TypeError, json.JSONDecodeError, AttributeError):
        return False


def _parse_gex_info(raw) -> dict | None:
    """Pull the B5 gex_info dict from the wrapped breakdown JSON. None for
    slow-only rows (cron writes the JSON), rows predating B5, or rows
    where the GEX fetch was empty / failed gracefully."""
    try:
        info = json.loads(raw).get("gex_info")  # type: ignore[union-attr]
        if not isinstance(info, dict):
            return None
        return info
    except (TypeError, json.JSONDecodeError, AttributeError):
        return None


async def fetch_latest_signal(
    pool: asyncpg.Pool,
    ticker: str,
    *,
    cal_map: dict | None = None,
) -> dict | None:
    """Latest signal for one ticker, fast-preferred with slow fallback.

    Returns a normalized dict with keys ticker, score, rating, confidence,
    breakdown (parsed list[dict]), fetched_at, partial - or None if the
    ticker is in neither table. rating/confidence are always populated:
    taken from the fast row, or derived for a slow-only (partial) row.

    cal_map: optional Phase 1c calibration map (suppress-only). Callers that
    already hold a pool should load it once with load_active_calibration(pool)
    and pass it in; callers that omit it get identity behaviour (raw confidence
    unchanged), which is the correct default for routes that do not yet load it.
    """
    ticker = ticker.upper()
    row = await pool.fetchrow(
        """
        WITH fast_row AS (
            SELECT ticker, composite AS score, rating, confidence,
                   breakdown, fetched_at, false AS partial
            FROM daily_signals_fast
            WHERE ticker = $1
                AND composite IS NOT NULL AND composite = composite
            ORDER BY date DESC, fetched_at DESC
            LIMIT 1
        ),
        slow_row AS (
            SELECT ticker, composite_partial AS score, NULL::text AS rating,
                   NULL::double precision AS confidence, breakdown,
                   fetched_at, true AS partial
            FROM daily_signals_slow
            WHERE ticker = $1
                AND composite_partial IS NOT NULL
                AND composite_partial = composite_partial
            ORDER BY date DESC, fetched_at DESC
            LIMIT 1
        )
        SELECT * FROM fast_row
        UNION ALL
        SELECT * FROM slow_row WHERE NOT EXISTS (SELECT 1 FROM fast_row)
        LIMIT 1
        """,
        ticker,
    )
    if row is None:
        return None

    breakdown = _parse_breakdown(row["breakdown"])
    score = _safe_float(row["score"])
    is_partial = bool(row["partial"])
    if is_partial:
        # Slow-only row: derive rating + confidence from the partial
        # composite + breakdown z's, exactly as the fast cron does.
        rating = map_to_tier(score)
        z_values = [
            z for e in breakdown if isinstance((z := e.get("z")), (int, float))
        ]
        confidence = calibrated_confidence(z_values, cal_map)
        # No band logic on slow-only rows (the cron that writes them never
        # sees a prev_rating to compare against). Always false.
        tier_flip_today = False
        gex_info = None
    else:
        # Fast row: stored confidence is a raw compute_confidence value from
        # write time; re-apply the calibration map at read time (single
        # application, not double-calibration) so fast rows are calibrated too.
        rating = row["rating"] or "HOLD"
        confidence = apply_calibration(_safe_float(row["confidence"]), cal_map)
        tier_flip_today = _parse_tier_flip(row["breakdown"])
        gex_info = _parse_gex_info(row["breakdown"])

    return {
        "ticker": row["ticker"],
        "score": score,
        "rating": rating,
        "confidence": confidence,
        "breakdown": breakdown,
        "fetched_at": row["fetched_at"],
        "partial": is_partial,
        "tier_flip_today": tier_flip_today,
        "gex_info": gex_info,
    }
