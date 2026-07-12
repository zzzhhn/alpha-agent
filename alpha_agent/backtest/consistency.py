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

from datetime import date as _date, timedelta

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


async def _fetch_live_outcomes(
    pool, tickers: list[str], *, after_date: "_date | None" = None
) -> list[tuple[str, "_date", bool]]:
    """(ticker, date, hit) for every REALIZED, DIRECTIONAL prediction in
    fast∪slow joined to its next-day return. HOLD and not-yet-realized rows are
    excluded (they never enter a hit-rate). `after_date` restricts to dates
    strictly greater than it — the unmaterialized recent tail. The tier for
    slow-only rows is derived exactly like the picks display path."""
    from alpha_agent.fusion.rating import map_to_tier

    if not tickers:
        return []
    params: list = [tickers]
    date_clause = ""
    if after_date is not None:
        params.append(after_date)
        date_clause = "AND p.date > $2"
    rows = await pool.fetch(
        f"""
        WITH px AS (
            SELECT ticker, date, close,
                   LEAD(close) OVER (PARTITION BY ticker ORDER BY date) AS next_close
            FROM daily_prices
            WHERE ticker = ANY($1::text[])
        ),
        preds AS (
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
        WHERE px.next_close IS NOT NULL {date_clause}
        """,
        *params,
    )
    out: list[tuple[str, "_date", bool]] = []
    for r in rows:
        fwd1 = r["fwd1"]
        if fwd1 is None:
            continue
        rating = r["rating"]
        if rating is None and r["score"] is not None:
            rating = map_to_tier(float(r["score"]))
        if rating is None:
            continue
        hit = _hit(rating, float(fwd1))
        if hit is None:
            continue
        out.append((r["ticker"], r["date"], hit))
    return out


async def materialize_outcomes(pool, *, full: bool = False) -> int:
    """Upsert realized directional outcomes into consistency_outcomes so the
    durable history survives any future prune of daily_signals_fast/slow. Called
    once for backfill (full=True) and daily by the daily_prices cron (full=False,
    which re-scans a short tail to catch late-realized predictions). Idempotent.
    Returns the number of rows upserted."""
    trows = await pool.fetch("SELECT DISTINCT ticker FROM daily_signals_slow")
    tickers = [r["ticker"] for r in trows]
    if not tickers:
        return 0
    after = None
    if not full:
        mx = await pool.fetchval("SELECT max(date) FROM consistency_outcomes")
        if mx is not None:
            after = mx - timedelta(days=10)  # re-scan tail for late realizations
    outcomes = await _fetch_live_outcomes(pool, tickers, after_date=after)
    if not outcomes:
        return 0
    await pool.executemany(
        "INSERT INTO consistency_outcomes (ticker, date, hit) VALUES ($1, $2, $3) "
        "ON CONFLICT (ticker, date) DO UPDATE SET hit = EXCLUDED.hit",
        outcomes,
    )
    return len(outcomes)


async def compute_window_tallies(
    pool, tickers: list[str]
) -> dict[str, dict[str, tuple[int, int]]]:
    """Return {ticker: {window: (hits, evaluated)}} raw tallies.

    Reads the DURABLE consistency_outcomes table (immune to signal pruning) for
    history, UNIONed with a live recompute of the recent tail (dates after the
    last materialized date) so the newest realized predictions are always counted
    even between materialization runs. If the table is missing/empty (e.g. before
    the V035 backfill), max_mat is None and the live path covers ALL dates — the
    original behavior, so there is no regression.
    """
    tallies: dict[str, dict[str, tuple[int, int]]] = {
        t: {w: (0, 0) for w in _ORDER} for t in tickers
    }
    if not tickers:
        return tallies

    date_rows = await pool.fetch(
        "SELECT DISTINCT date FROM daily_prices ORDER BY date DESC LIMIT 252"
    )
    if not date_rows:
        return tallies
    dates: list[_date] = [r["date"] for r in date_rows]
    cutoffs: dict[str, _date] = {
        w: dates[min(n - 1, len(dates) - 1)] for w, n in WINDOW_TRADING_DAYS.items()
    }

    outcomes: list[tuple[str, _date, bool]] = []
    max_mat: _date | None = None
    try:
        mat = await pool.fetch(
            "SELECT ticker, date, hit FROM consistency_outcomes "
            "WHERE ticker = ANY($1::text[])",
            tickers,
        )
        outcomes = [(r["ticker"], r["date"], r["hit"]) for r in mat]
        max_mat = max((d for _, d, _ in outcomes), default=None)
    except Exception:  # noqa: BLE001 — table not yet created: pure-live fallback
        outcomes = []
        max_mat = None
    outcomes += await _fetch_live_outcomes(pool, tickers, after_date=max_mat)

    counts: dict[str, dict[str, list[int]]] = {
        t: {w: [0, 0] for w in _ORDER} for t in tickers
    }
    for ticker, d, hit in outcomes:
        if ticker not in counts:
            continue
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
