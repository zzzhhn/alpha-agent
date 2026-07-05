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


async def compute_window_tallies(
    pool, tickers: list[str]
) -> dict[str, dict[str, tuple[int, int]]]:
    """Return {ticker: {window: (hits, evaluated)}} raw tallies.

    Prediction history is the UNION of BOTH signal tables, deduped per
    (ticker, date) preferring fast:
      - daily_signals_fast rows carry the true stored rating (sticky tier) —
        authoritative when present, incl. HOLD (= no directional call that day).
      - daily_signals_slow rows (the full-universe daily sweep) carry only
        composite_partial; their tier is derived via fusion.rating.map_to_tier —
        the SAME derivation the picks page uses to display slow-only rows.
    Reading only the fast table made every long-tail / newly-risen ticker show
    all-dash: its real daily history lived in slow and was ignored.
    """
    from alpha_agent.fusion.rating import map_to_tier

    tallies: dict[str, dict[str, tuple[int, int]]] = {
        t: {w: (0, 0) for w in _ORDER} for t in tickers
    }
    if not tickers:
        return tallies

    # Market-calendar cutoffs: the Nth most recent trading date overall. Using
    # the global date list (not per-ticker) keeps "past N trading days" the same
    # sessions for every row even when a ticker has gaps.
    date_rows = await pool.fetch(
        "SELECT DISTINCT date FROM daily_prices ORDER BY date DESC LIMIT 252"
    )
    if not date_rows:
        return tallies
    dates: list[_date] = [r["date"] for r in date_rows]
    cutoffs: dict[str, _date] = {
        w: dates[min(n - 1, len(dates) - 1)] for w, n in WINDOW_TRADING_DAYS.items()
    }

    # Evaluated rows: each stored prediction joined to its realized next-day
    # return. Not-yet-realized (next_close NULL) rows are dropped in SQL; the
    # direction call (incl. HOLD-exclusion) resolves in Python because slow rows
    # need the tier derived from their score.
    rows = await pool.fetch(
        """
        WITH px AS (
            SELECT ticker, date, close,
                   LEAD(close) OVER (PARTITION BY ticker ORDER BY date) AS next_close
            FROM daily_prices
            WHERE ticker = ANY($1::text[])
        ),
        preds AS (
            -- One prediction per (ticker, date): fast (true rating) preferred,
            -- newest fetched_at within a source breaks intraday ties.
            SELECT DISTINCT ON (ticker, date) ticker, date, rating, score
            FROM (
                SELECT ticker, date, rating, composite AS score,
                       1 AS pri, fetched_at
                FROM daily_signals_fast
                WHERE ticker = ANY($1::text[])
                UNION ALL
                SELECT ticker, date, NULL::text AS rating,
                       composite_partial AS score, 0 AS pri, fetched_at
                FROM daily_signals_slow
                WHERE ticker = ANY($1::text[])
                  AND composite_partial IS NOT NULL
                  AND composite_partial = composite_partial
            ) u
            ORDER BY ticker, date, pri DESC, fetched_at DESC
        )
        SELECT p.ticker, p.date, p.rating, p.score,
               (px.next_close / NULLIF(px.close, 0) - 1.0) AS fwd1
        FROM preds p
        JOIN px ON px.ticker = p.ticker AND px.date = p.date
        WHERE px.next_close IS NOT NULL
        """,
        tickers,
    )

    # counts[ticker][window] = [hits, total]
    counts: dict[str, dict[str, list[int]]] = {
        t: {w: [0, 0] for w in _ORDER} for t in tickers
    }
    for r in rows:
        ticker = r["ticker"]
        if ticker not in counts:
            continue
        fwd1 = r["fwd1"]
        if fwd1 is None:
            continue
        rating = r["rating"]
        if rating is None and r["score"] is not None:
            # Slow-only day: derive the tier from the partial composite exactly
            # like the picks display path does. HOLD -> no directional call.
            rating = map_to_tier(float(r["score"]))
        if rating is None:
            continue
        hit = _hit(rating, float(fwd1))
        if hit is None:
            continue
        d = r["date"]
        for w in _ORDER:
            if w == "hist" or d >= cutoffs[w]:
                bucket = counts[ticker][w]
                bucket[1] += 1
                if hit:
                    bucket[0] += 1

    for ticker, per_window in counts.items():
        tallies[ticker] = {w: (v[0], v[1]) for w, v in per_window.items()}
    return tallies


def rates_from_tallies(
    tallies: dict[str, dict[str, tuple[int, int]]],
) -> dict[str, dict[str, float | None]]:
    """Tallies -> {ticker: {window: rate-or-None}} applying MIN_SAMPLES."""
    return {
        t: {w: _rate(h, n, w) for w, (h, n) in per_window.items()}
        for t, per_window in tallies.items()
    }


async def compute_window_consistency(
    pool, tickers: list[str]
) -> dict[str, dict[str, float | None]]:
    """Return {ticker: {"d5":.., "m1":.., "y1":.., "hist":..}} hit-rates.

    Each value is a fraction in [0,1] or None (insufficient data -> dash).
    Tickers with no realized directional predictions map to all-None.
    """
    return rates_from_tallies(await compute_window_tallies(pool, tickers))
