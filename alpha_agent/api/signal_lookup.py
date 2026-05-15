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

from alpha_agent.fusion.rating import compute_confidence, map_to_tier


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


async def fetch_latest_signal(pool: asyncpg.Pool, ticker: str) -> dict | None:
    """Latest signal for one ticker, fast-preferred with slow fallback.

    Returns a normalized dict with keys ticker, score, rating, confidence,
    breakdown (parsed list[dict]), fetched_at, partial - or None if the
    ticker is in neither table. rating/confidence are always populated:
    taken from the fast row, or derived for a slow-only (partial) row.
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
        confidence = compute_confidence(z_values)
    else:
        rating = row["rating"] or "HOLD"
        confidence = _safe_float(row["confidence"])

    return {
        "ticker": row["ticker"],
        "score": score,
        "rating": rating,
        "confidence": confidence,
        "breakdown": breakdown,
        "fetched_at": row["fetched_at"],
        "partial": is_partial,
    }
