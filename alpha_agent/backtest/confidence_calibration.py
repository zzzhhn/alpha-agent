# alpha_agent/backtest/confidence_calibration.py
"""Phase 1c confidence calibration.

Measures realized directional hit-rate per stated confidence (reliability
curve + Brier), fits a monotone isotonic map (numpy PAVA, no sklearn), and
applies it on the live read path to suppress overconfidence only. The daily
cron appends a fresh calibration row; the read path loads the latest.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np  # noqa: F401  (used by later calibration tasks in this module)

MIN_PAIRS: int = 50          # below this, fall back to identity (no recalibration)
FIT_WINDOW_DAYS: int = 90    # rolling fit window; uses all available if < this
_FWD_DAYS: int = 5
_UP_TIERS = frozenset({"BUY", "OW"})
_DOWN_TIERS = frozenset({"UW", "SELL"})


def _hit(rating: str, fwd_5d: float) -> bool | None:
    """True/False if the rating's directional call matched the realized
    forward 5-day return sign; None for HOLD (excluded from calibration).
    Pure sign match, no deadband: a non-positive return fails an up-call."""
    if rating in _UP_TIERS:
        return fwd_5d > 0
    if rating in _DOWN_TIERS:
        return fwd_5d < 0
    return None


async def gather_confidence_hits(pool, window_days: int = FIT_WINDOW_DAYS) -> list[tuple[float, int]]:
    """Return [(stated_confidence, hit01), ...] over the rolling window: each
    non-HOLD daily_signals_fast row with an observable 5-trading-day forward
    return (from daily_prices) contributes one pair. hit01 is 1/0."""
    now = datetime.now(UTC)
    window_start = (now - timedelta(days=window_days)).date()
    fwd_cutoff = (now - timedelta(days=_FWD_DAYS)).date()
    rows = await pool.fetch(
        """
        WITH fwd AS (
            SELECT ticker, date, close AS ce,
                   LEAD(close, 5) OVER (PARTITION BY ticker ORDER BY date) AS cx
            FROM daily_prices
        )
        SELECT f.rating, f.confidence,
               (fwd.cx / fwd.ce - 1)::double precision AS fwd_5d
        FROM daily_signals_fast f
        JOIN fwd ON fwd.ticker = f.ticker AND fwd.date = f.date
        WHERE f.date >= $1 AND f.date <= $2
          AND f.rating IS NOT NULL AND f.confidence IS NOT NULL
          AND fwd.ce > 0 AND fwd.cx IS NOT NULL
        """,
        window_start, fwd_cutoff,
    )
    pairs: list[tuple[float, int]] = []
    for r in rows:
        h = _hit(r["rating"], float(r["fwd_5d"]))
        if h is None:
            continue
        pairs.append((float(r["confidence"]), 1 if h else 0))
    return pairs
