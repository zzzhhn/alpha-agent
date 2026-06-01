"""Universe-wide dimension grade thresholds, fetched once and memoized.

grade_dimensions needs the cross-sectional distribution of every dimension, but
the picks list endpoint only queries the returned subset (a pre-selected top-N,
which would re-compress the grades). So thresholds must come from the FULL
universe, independent of any one request's filter or limit. Both /picks and the
single-stock route call get_dimension_thresholds so they grade on the same
basis.

Cost control: the universe is ~550 rows of breakdown JSON. We memoize the
computed thresholds in-process for a few minutes. On Vercel Fluid Compute warm
instances this means at most one universe scan per cache window; a cold
instance recomputes once. Thresholds drift slowly (they track the daily/fast
cron), so a few-minute staleness is harmless. If QPS ever makes the scan a
bottleneck, precompute the thresholds in the cron and store one row instead.
"""
from __future__ import annotations

import json
import time
from typing import Any

import asyncpg

from alpha_agent.fusion.grades import compute_dimension_thresholds

# Latest breakdown per ticker across the whole universe, fast taking precedence
# over slow (same dedup as the picks route), with NO limit or search filter.
_UNIVERSE_SQL = """
WITH fast_latest AS (
    SELECT DISTINCT ON (ticker) ticker, breakdown
    FROM daily_signals_fast
    WHERE composite IS NOT NULL AND composite = composite
    ORDER BY ticker, date DESC, fetched_at DESC
),
slow_latest AS (
    SELECT DISTINCT ON (ticker) ticker, breakdown
    FROM daily_signals_slow
    WHERE composite_partial IS NOT NULL AND composite_partial = composite_partial
    ORDER BY ticker, date DESC, fetched_at DESC
)
SELECT breakdown FROM fast_latest
UNION ALL
SELECT s.breakdown FROM slow_latest s
WHERE NOT EXISTS (SELECT 1 FROM fast_latest f WHERE f.ticker = s.ticker)
"""

_TTL_SECONDS = 600.0
# Deliberate process-local memo (not data mutation): keeps the universe scan
# off the hot path. Each serverless instance keeps its own copy.
_cache: dict[str, Any] = {"ts": None, "val": None}


async def get_dimension_thresholds(
    pool: asyncpg.Pool,
) -> dict[str, list[float] | None]:
    """Memoized per-dimension band breakpoints over the full universe."""
    now = time.monotonic()
    if _cache["val"] is not None and _cache["ts"] is not None:
        if (now - _cache["ts"]) < _TTL_SECONDS:
            return _cache["val"]

    rows = await pool.fetch(_UNIVERSE_SQL)
    breakdowns: list[list[dict]] = []
    for r in rows:
        raw = r["breakdown"]
        try:
            parsed = json.loads(raw) if isinstance(raw, str) else raw
            breakdowns.append(parsed.get("breakdown", []))
        except (TypeError, AttributeError, json.JSONDecodeError):
            continue

    thresholds = compute_dimension_thresholds(breakdowns)
    _cache["val"] = thresholds
    _cache["ts"] = now
    return thresholds
