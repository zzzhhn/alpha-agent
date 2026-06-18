"""Per-ticker directional consistency over trailing windows.

"Consistency" = how often the engine's predicted direction for a stock matched
the stock's actual next-trading-day move, measured over a trailing window of
prediction dates. This is the per-stock, multi-window generalization of the
single calibrated "hit" number the picks table already shows.

Definition (locked with the user 2026-06-18):
  - predicted direction on date d = the stored rating tier in daily_signals_fast:
      BUY/OW -> up call, UW/SELL -> down call, HOLD -> excluded (no directional call).
  - actual direction = sign of the NEXT trading day's return,
      next_close / close - 1, where next_close is the following row in
      daily_prices for that ticker (so it respects the market calendar, not
      calendar+1). A prediction whose next day has not happened yet (next_close
      IS NULL) is NOT YET realized and is excluded.
  - a window's hit-rate = hits / evaluated, over prediction dates inside that
      trailing window. Below MIN_SAMPLES[window] evaluated predictions the
      window is reported as None (the UI shows a dash) so a thin or absent
      history never renders a misleadingly precise number.

Windows are trailing trading-day counts measured against the market calendar
(distinct dates in daily_prices), NOT per-ticker row counts, so "past 5 trading
days" means the same 5 calendar sessions for every ticker.
"""
from __future__ import annotations

from datetime import date as _date

from alpha_agent.backtest.confidence_calibration import _DOWN_TIERS, _UP_TIERS

# Trailing window sizes in trading days. "hist" (all-time) has no cutoff.
WINDOW_TRADING_DAYS: dict[str, int] = {"d5": 5, "m1": 21, "y1": 252}

# Minimum evaluated (realized, non-HOLD) predictions a window needs before it
# shows a number instead of a dash. Roughly "enough of the window is filled":
# ~half a year for y1 keeps it a dash until the prediction history is deep
# enough for the number to mean something, rather than silently equalling hist.
MIN_SAMPLES: dict[str, int] = {"d5": 3, "m1": 10, "y1": 120, "hist": 5}

_ORDER: tuple[str, ...] = ("d5", "m1", "y1", "hist")


def _hit(rating: str, fwd1: float) -> bool | None:
    """True/False if the tier's directional call matched the next-day return
    sign; None for HOLD / unknown tiers (excluded from the rate)."""
    if rating in _UP_TIERS:
        return fwd1 > 0
    if rating in _DOWN_TIERS:
        return fwd1 < 0
    return None


def _rate(hits: int, total: int, window: str) -> float | None:
    if total < MIN_SAMPLES[window]:
        return None
    return hits / total


async def compute_window_consistency(
    pool, tickers: list[str]
) -> dict[str, dict[str, float | None]]:
    """Return {ticker: {"d5":.., "m1":.., "y1":.., "hist":..}} hit-rates.

    Each value is a fraction in [0,1] or None (insufficient data -> dash).
    Tickers with no realized directional predictions map to all-None.
    """
    empty = {w: None for w in _ORDER}
    result: dict[str, dict[str, float | None]] = {t: dict(empty) for t in tickers}
    if not tickers:
        return result

    # Market-calendar cutoffs: the Nth most recent trading date overall. Using
    # the global date list (not per-ticker) keeps "past N trading days" the same
    # sessions for every row even when a ticker has gaps.
    date_rows = await pool.fetch(
        "SELECT DISTINCT date FROM daily_prices ORDER BY date DESC LIMIT 252"
    )
    if not date_rows:
        return result
    dates: list[_date] = [r["date"] for r in date_rows]
    cutoffs: dict[str, _date] = {
        w: dates[min(n - 1, len(dates) - 1)] for w, n in WINDOW_TRADING_DAYS.items()
    }

    # Evaluated rows: each stored prediction joined to its realized next-day
    # return. HOLD and not-yet-realized (next_close NULL) rows are dropped in SQL.
    rows = await pool.fetch(
        """
        WITH px AS (
            SELECT ticker, date, close,
                   LEAD(close) OVER (PARTITION BY ticker ORDER BY date) AS next_close
            FROM daily_prices
            WHERE ticker = ANY($1::text[])
        )
        SELECT s.ticker, s.date, s.rating,
               (px.next_close / NULLIF(px.close, 0) - 1.0) AS fwd1
        FROM daily_signals_fast s
        JOIN px ON px.ticker = s.ticker AND px.date = s.date
        WHERE s.ticker = ANY($1::text[])
          AND px.next_close IS NOT NULL
          AND s.rating IN ('BUY', 'OW', 'UW', 'SELL')
        """,
        tickers,
    )

    # tallies[ticker][window] = [hits, total]
    tallies: dict[str, dict[str, list[int]]] = {
        t: {w: [0, 0] for w in _ORDER} for t in tickers
    }
    for r in rows:
        ticker = r["ticker"]
        if ticker not in tallies:
            continue
        fwd1 = r["fwd1"]
        if fwd1 is None:
            continue
        hit = _hit(r["rating"], float(fwd1))
        if hit is None:
            continue
        d = r["date"]
        for w in _ORDER:
            if w == "hist" or d >= cutoffs[w]:
                bucket = tallies[ticker][w]
                bucket[1] += 1
                if hit:
                    bucket[0] += 1

    for ticker, per_window in tallies.items():
        result[ticker] = {
            w: _rate(per_window[w][0], per_window[w][1], w) for w in _ORDER
        }
    return result
