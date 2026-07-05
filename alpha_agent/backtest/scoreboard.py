"""Portfolio-level picks scoreboard: the honest answer to "does the composite
have real signal?".

Per-stock NEXT-DAY direction (the consistency column) is the wrong yardstick for
a composite built from weeks-to-months signals: any daily cross-sectional factor
tops out near coin-flip there. The claim a factor framework actually makes is
CROSS-SECTIONAL: the names it ranks top should, as a BASKET, outperform the
universe average (and the names it ranks bottom should underperform). This module
reconstructs, for each of the trailing N trading days, the top-K / bottom-K
baskets by the composite as stored THAT day (fast∪slow, no lookahead) and scores
their next-day forward returns against two baselines:

  - market   = equal-weight universe-average return (beat the market, not zero);
  - base_rate = fraction of positive stock-days (the "always guess up" hit rate —
    a 52% long hit-rate is WORSE than blind if 54% of stock-days rose).

Overlap note: consecutive daily baskets share names, so day returns are not
independent samples; the cumulative numbers are descriptive, not a t-stat.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Scoreboard:
    days: int                 # trading days actually evaluated
    top_n: int
    long_cum: float           # cumulative return of the daily top-K basket
    short_cum: float          # cumulative return of the daily bottom-K basket
    market_cum: float         # equal-weight universe average, same days
    spread_cum: float         # long minus short, compounded daily
    long_hit_rate: float | None   # fraction of basket stock-days that rose
    base_rate: float | None       # fraction of ALL stock-days that rose


async def compute_picks_scoreboard(
    pool, *, top_n: int = 10, days: int = 21
) -> Scoreboard | None:
    """Reconstruct daily top/bottom baskets from stored signals and score them.

    Returns None when there is not enough realized history (fewer than 3
    evaluated days). One SQL pass: per (date) the composite ranking as stored
    that day (fast preferred over slow per ticker+date), joined to realized
    next-day returns.
    """
    rows = await pool.fetch(
        """
        WITH px AS (
            SELECT ticker, date, close,
                   LEAD(close) OVER (PARTITION BY ticker ORDER BY date) AS next_close
            FROM daily_prices
        ),
        preds AS (
            SELECT DISTINCT ON (ticker, date) ticker, date, score
            FROM (
                SELECT ticker, date, composite AS score, 1 AS pri, fetched_at
                FROM daily_signals_fast
                WHERE composite IS NOT NULL AND composite = composite
                UNION ALL
                SELECT ticker, date, composite_partial AS score, 0 AS pri, fetched_at
                FROM daily_signals_slow
                WHERE composite_partial IS NOT NULL
                  AND composite_partial = composite_partial
            ) u
            ORDER BY ticker, date, pri DESC, fetched_at DESC
        ),
        evaluated AS (
            SELECT p.ticker, p.date, p.score,
                   (px.next_close / NULLIF(px.close, 0) - 1.0) AS fwd1
            FROM preds p
            JOIN px ON px.ticker = p.ticker AND px.date = p.date
            WHERE px.next_close IS NOT NULL
        ),
        recent_dates AS (
            SELECT DISTINCT date FROM evaluated ORDER BY date DESC LIMIT $1
        )
        SELECT e.date, e.ticker, e.score, e.fwd1,
               RANK() OVER (PARTITION BY e.date ORDER BY e.score DESC) AS rk_top,
               RANK() OVER (PARTITION BY e.date ORDER BY e.score ASC)  AS rk_bot,
               COUNT(*) OVER (PARTITION BY e.date) AS n_names
        FROM evaluated e
        JOIN recent_dates rd ON rd.date = e.date
        """,
        days,
    )
    if not rows:
        return None

    # Per-date aggregation in Python (few thousand rows).
    by_date: dict = {}
    for r in rows:
        d = r["date"]
        b = by_date.setdefault(
            d, {"long": [], "short": [], "all": [], "n_names": int(r["n_names"])}
        )
        fwd1 = float(r["fwd1"])
        b["all"].append(fwd1)
        if int(r["rk_top"]) <= top_n:
            b["long"].append(fwd1)
        if int(r["rk_bot"]) <= top_n:
            b["short"].append(fwd1)

    long_cum = short_cum = market_cum = spread_cum = 1.0
    long_up = long_total = all_up = all_total = 0
    evaluated_days = 0
    for d in sorted(by_date):
        b = by_date[d]
        # A day needs enough breadth for "top-K vs universe" to mean anything.
        if b["n_names"] < top_n * 3 or not b["long"] or not b["short"]:
            continue
        evaluated_days += 1
        lr = sum(b["long"]) / len(b["long"])
        sr = sum(b["short"]) / len(b["short"])
        mr = sum(b["all"]) / len(b["all"])
        long_cum *= 1.0 + lr
        short_cum *= 1.0 + sr
        market_cum *= 1.0 + mr
        spread_cum *= 1.0 + (lr - sr)
        long_up += sum(1 for x in b["long"] if x > 0)
        long_total += len(b["long"])
        all_up += sum(1 for x in b["all"] if x > 0)
        all_total += len(b["all"])

    if evaluated_days < 3:
        return None
    return Scoreboard(
        days=evaluated_days,
        top_n=top_n,
        long_cum=long_cum - 1.0,
        short_cum=short_cum - 1.0,
        market_cum=market_cum - 1.0,
        spread_cum=spread_cum - 1.0,
        long_hit_rate=(long_up / long_total) if long_total else None,
        base_rate=(all_up / all_total) if all_total else None,
    )
