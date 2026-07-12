"""GET /api/picks/edge — long-short basket edge across horizons.

Why this exists (the metric choice rationale): the per-name 5-day directional
hit-rate is ~coin-flip — markets are near-efficient short-term, so single-ticker
direction is honestly indistinguishable from noise. The engine's REAL,
statistically-meaningful edge is the LONG-SHORT BASKET: rank the universe by the
composite score, then compare the top names against the bottom names. The
long-short spread is BETA-NEUTRAL (market drift cancels between the longs and
the shorts), so unlike single-name direction it stays honest to measure at
longer horizons (5 / 20 / 60 trading days).

For each horizon h, over a trailing window of the most recent ~90 trading
dates that have an observable forward return:
  - rank_IC   = Spearman rank correlation(composite, fwd_ret_h) per date.
  - long_short_spread = mean(fwd_ret_h | top quintile by composite)
                        - mean(fwd_ret_h | bottom quintile by composite).
  - aggregate: mean_ic, ic_ir (= mean_ic / std(per-date ICs)), mean_spread.

Honesty contract: if a horizon has fewer than ~10 usable dates (the
daily_signals_fast history is currently only ~3 weeks long, so the 20d/60d
forward windows have no observable exits yet), the horizon is returned with
null metrics + an `insufficient` flag and the real n_days. We NEVER fabricate
an edge to fill the slot.

Cost: this is a heavy transpacific scan (the function runs in hkg1, the DB is in
us-east-1). The whole computation is memoized process-locally with a ~600s TTL,
mirroring alpha_agent/fusion/grade_thresholds.py.
"""
from __future__ import annotations

import math
import time
from datetime import UTC, datetime
from typing import Any

import numpy as np
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from alpha_agent.api.dependencies import get_db_pool
from alpha_agent.backtest.ic_engine import _spearman_rho
from alpha_agent.backtest.scoreboard import _newey_west_se, _nw_lag

router = APIRouter(prefix="/api/picks", tags=["picks"])

# Horizons in trading days. 5d is the short-window signal alignment; 20d/60d
# probe whether the rank edge persists (decays / strengthens) over longer holds.
_HORIZONS: tuple[int, ...] = (5, 20, 60)
# Trailing window of as-of dates to aggregate per horizon. The DB rarely has
# this many for the fast table today, so it acts as an upper bound.
_WINDOW_DATES: int = 90
# Per-date universe-breadth floor: a cross-sectional IC / quintile split is
# meaningless on a handful of names.
_MIN_TICKERS_PER_DATE: int = 20
# Honesty floor: below this many usable dates the aggregate is statistically
# empty -> report insufficient rather than a noisy point estimate.
_MIN_DATES: int = 10
# Quintile = top/bottom 20%.
_QUINTILE_FRAC: float = 0.2

_TTL_SECONDS: float = 600.0
# Deliberate process-local memo (not data mutation): keeps the heavy
# transpacific scan off the hot path. Each serverless instance keeps its own
# copy; a few-minute staleness is harmless (the metric tracks the daily cron).
_cache: dict[str, Any] = {"ts": None, "val": None}


# Per-horizon composite + forward-return rows. The composite is the EOD value
# per (ticker, date), taken from the UNION of BOTH signal tables — fast (true
# composite, top-~240 intraday names) preferred over slow (composite_partial,
# full universe daily) on the same day. Reading only fast capped the usable
# history at ~3 weeks and starved the 20d/60d horizons into permanent
# "insufficient"; the slow sweep's deeper full-universe daily history is exactly
# what those horizons need. The forward return is LEAD(close, h) over
# daily_prices, joined back on (ticker, date). Rows without an observable
# forward close (LEAD null) drop out honestly.
_EDGE_SQL = """
WITH comp AS (
    SELECT DISTINCT ON (ticker, date)
        ticker, date, composite
    FROM (
        SELECT ticker, date, composite, 1 AS pri, fetched_at
        FROM daily_signals_fast
        WHERE composite IS NOT NULL AND composite = composite
        UNION ALL
        SELECT ticker, date, composite_partial AS composite, 0 AS pri, fetched_at
        FROM daily_signals_slow
        WHERE composite_partial IS NOT NULL
          AND composite_partial = composite_partial
    ) u
    ORDER BY ticker, date, pri DESC, fetched_at DESC
),
fwd AS (
    SELECT
        ticker,
        date,
        close,
        LEAD(close, $1) OVER (PARTITION BY ticker ORDER BY date) AS close_fwd
    FROM daily_prices
)
SELECT
    c.date,
    c.composite::double precision AS composite,
    (f.close_fwd / f.close - 1.0)::double precision AS fwd_ret
FROM comp c
JOIN fwd f
  ON f.ticker = c.ticker
 AND f.date = c.date
WHERE f.close > 0
  AND f.close_fwd IS NOT NULL
"""


class HorizonEdge(BaseModel):
    horizon: int
    mean_ic: float | None
    ic_ir: float | None
    long_short_spread: float | None
    n_days: int
    insufficient: bool
    # 2026-07-12: IC significance fields (display-only, do not affect ranking)
    ic_t_stat: float | None = None      # Newey-West t-stat of mean IC
    ic_t_gt2: bool | None = None        # |t| > 2.0 (conventional significance)
    ic_t_gt3: bool | None = None        # |t| > 3.0 (Harvey-Liu-Zhu multiple-testing)


class BasketEdgeResponse(BaseModel):
    as_of: str
    universe_n: int
    horizons: list[HorizonEdge]


def _clean(v: float | None) -> float | None:
    """NaN/Inf/None -> None. JSON can't carry IEEE non-finite values, and a
    degenerate per-date IC (constant composite) yields NaN from numpy."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def _horizon_from_rows(horizon: int, rows: list[Any]) -> HorizonEdge:
    """Aggregate per-date rank-IC and long-short quintile spread for one
    horizon. `rows` are (date, composite, fwd_ret) for that horizon only."""
    by_date: dict[Any, list[tuple[float, float]]] = {}
    for r in rows:
        comp = _clean(r["composite"])
        ret = _clean(r["fwd_ret"])
        if comp is None or ret is None:
            continue
        by_date.setdefault(r["date"], []).append((comp, ret))

    per_ic: list[float] = []
    per_spread: list[float] = []
    # Most-recent window of dates that clear the breadth floor.
    for d in sorted(by_date.keys())[-_WINDOW_DATES:]:
        pairs = by_date[d]
        if len(pairs) < _MIN_TICKERS_PER_DATE:
            continue
        comps = [p[0] for p in pairs]
        rets = [p[1] for p in pairs]
        ic = _spearman_rho(comps, rets)
        if ic is None or math.isnan(ic):
            continue
        ordered = sorted(pairs, key=lambda p: p[0])
        k = max(1, int(len(ordered) * _QUINTILE_FRAC))
        bottom = ordered[:k]
        top = ordered[-k:]
        spread = float(np.mean([p[1] for p in top]) - np.mean([p[1] for p in bottom]))
        if math.isnan(spread) or math.isinf(spread):
            continue
        per_ic.append(float(ic))
        per_spread.append(spread)

    n_days = len(per_ic)
    if n_days < _MIN_DATES:
        # Honest insufficient: report the real count, null the metrics.
        return HorizonEdge(
            horizon=horizon,
            mean_ic=None,
            ic_ir=None,
            long_short_spread=None,
            n_days=n_days,
            insufficient=True,
        )

    mean_ic = float(np.mean(per_ic))
    # ic_ir = mean_ic / std(per-date ICs); null when < 2 dates or zero spread.
    ic_ir: float | None = None
    ic_t: float | None = None
    if n_days >= 2:
        ic_std = float(np.std(per_ic, ddof=1))
        if ic_std > 0:
            ic_ir = mean_ic / ic_std
        # Newey-West t-stat for mean IC (same HAC lag rule as scoreboard)
        ic_arr = np.array(per_ic, dtype=float)
        residuals = ic_arr - mean_ic
        lag = _nw_lag(n_days)
        nw_se = _newey_west_se(residuals, np.ones(n_days), lag)
        if nw_se > 0:
            ic_t = mean_ic / nw_se
    mean_spread = float(np.mean(per_spread))

    return HorizonEdge(
        horizon=horizon,
        mean_ic=_clean(mean_ic),
        ic_ir=_clean(ic_ir),
        long_short_spread=_clean(mean_spread),
        n_days=n_days,
        insufficient=False,
        ic_t_stat=_clean(ic_t),
        ic_t_gt2=(abs(ic_t) > 2.0) if ic_t is not None and not math.isnan(ic_t) else None,
        ic_t_gt3=(abs(ic_t) > 3.0) if ic_t is not None and not math.isnan(ic_t) else None,
    )


async def _compute_edge() -> BasketEdgeResponse:
    pool = await get_db_pool()
    # Universe breadth across BOTH tables (matches what _EDGE_SQL now scans).
    universe_n = await pool.fetchval(
        "SELECT count(DISTINCT ticker) FROM ("
        "  SELECT ticker FROM daily_signals_fast"
        "  WHERE composite IS NOT NULL AND composite = composite"
        "  UNION"
        "  SELECT ticker FROM daily_signals_slow"
        "  WHERE composite_partial IS NOT NULL"
        "    AND composite_partial = composite_partial"
        ") u"
    )
    horizons: list[HorizonEdge] = []
    for h in _HORIZONS:
        rows = await pool.fetch(_EDGE_SQL, h)
        horizons.append(_horizon_from_rows(h, list(rows)))
    return BasketEdgeResponse(
        as_of=datetime.now(UTC).isoformat(),
        universe_n=int(universe_n or 0),
        horizons=horizons,
    )


@router.get("/edge", response_model=BasketEdgeResponse)
async def picks_edge() -> BasketEdgeResponse:
    """Long-short basket edge (rank-IC + quintile spread) per horizon.

    Pure read, no auth (same as /api/picks/lean). Memoized ~600s process-local.
    """
    import traceback

    now = time.monotonic()
    cached = _cache["val"]
    cached_ts = _cache["ts"]
    if cached is not None and cached_ts is not None:
        if (now - cached_ts) < _TTL_SECONDS:
            return cached  # type: ignore[return-value]

    try:
        result = await _compute_edge()
    except Exception as e:
        # Surface the real exception (Silent Exception Anti-Pattern): a generic
        # 500 turns one root cause into N derived symptoms.
        raise HTTPException(
            status_code=500,
            detail=(
                f"picks_edge failed: {type(e).__name__}: {e}\n"
                f"{traceback.format_exc()[:1500]}"
            ),
        ) from e

    _cache["val"] = result
    _cache["ts"] = now
    return result
