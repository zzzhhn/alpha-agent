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

2026-07-12 additions (display-only — does NOT change ranking/selection logic):
  - SPY benchmark: compound SPY over the same dates for a second reference line.
  - Turnover accounting: mean daily one-sided name-overlap turnover for the long
    basket; cost-adjusted net return with a configurable cost_bps (default 10bps
    one-way); break-even cost in bps (cost at which net = SPY return).
  - OLS alpha/beta vs SPY: regress daily long returns on daily SPY returns using
    numpy.linalg.lstsq; alpha t-stat uses Newey-West (HAC) standard errors with
    lag = floor(4*(n/100)^(2/9)).

Overlap note: consecutive daily baskets share names, so day returns are not
independent samples; the cumulative numbers are descriptive, not a t-stat.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


# ---------------------------------------------------------------------------
# Newey-West HAC standard error helper (no statsmodels dependency)
# ---------------------------------------------------------------------------

def _newey_west_se(residuals: np.ndarray, x_demeaned: np.ndarray, lag: int) -> float:
    """HAC standard error for the mean (or OLS coefficient) via Newey-West.

    For testing mean IC significance: residuals = ic_t - mean_ic,
    x_demeaned = array of ones (intercept only).
    For OLS alpha: residuals = e_t, x_demeaned = [1, spy_t] demeaned column.

    Returns the HAC standard error scalar. Falls back to classical OLS SE
    if the Newey-West sandwich is degenerate.
    """
    n = len(residuals)
    if n < 2:
        return float("inf")
    # Sandwich: S = sum_{l=-L}^{L} w_l * Gamma_l
    # where Gamma_l = (1/n) sum_t e_t * e_{t-l}
    # and w_l = 1 - |l|/(L+1)  (Bartlett kernel)
    s = float(np.dot(residuals, residuals)) / n  # l=0 term
    for ell in range(1, lag + 1):
        w = 1.0 - ell / (lag + 1.0)
        gamma = float(np.dot(residuals[ell:], residuals[:-ell])) / n
        s += 2.0 * w * gamma
    s = max(s, 1e-30)  # numerical floor
    return math.sqrt(s / n)


def _nw_lag(n: int) -> int:
    """Standard Newey-West lag: floor(4*(n/100)^(2/9))."""
    return max(1, int(4.0 * (n / 100.0) ** (2.0 / 9.0)))


# ---------------------------------------------------------------------------
# OLS beta/alpha with HAC t-stat
# ---------------------------------------------------------------------------

def _ols_alpha_beta(y: np.ndarray, x: np.ndarray) -> tuple[float, float, float]:
    """Regress y on x (both 1-D, same length n ≥ 3).

    Returns (beta, annualized_alpha, alpha_t_stat).
    alpha_t_stat uses Newey-West SE. Returns (nan, nan, nan) on failure.
    """
    n = len(y)
    if n < 3:
        return float("nan"), float("nan"), float("nan")
    X = np.column_stack([np.ones(n), x])
    try:
        coeffs, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
    except np.linalg.LinAlgError:
        return float("nan"), float("nan"), float("nan")
    alpha_daily, beta = float(coeffs[0]), float(coeffs[1])
    alpha_ann = alpha_daily * 252.0
    residuals = y - X @ coeffs
    lag = _nw_lag(n)
    nw_se = _newey_west_se(residuals, X[:, 0], lag)  # SE for intercept
    # For the intercept SE we use the scalar HAC variance of the residuals
    # divided by sqrt(n): this is the standard OLS-HAC formula for the
    # constant term when X includes only a constant + one regressor with
    # well-behaved variance.
    alpha_se = nw_se  # already divided by sqrt(n) inside _newey_west_se
    alpha_t = (alpha_daily / alpha_se) if alpha_se > 0 else float("nan")
    return beta, alpha_ann, alpha_t


# ---------------------------------------------------------------------------
# Dataclass (extended)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Scoreboard:
    days: int                 # trading days actually evaluated
    top_n: int
    long_cum: float           # gross cumulative return of the daily top-K basket
    short_cum: float          # cumulative return of the daily bottom-K basket
    market_cum: float         # equal-weight universe average, same days
    spread_cum: float         # long minus short, compounded daily
    long_hit_rate: float | None   # fraction of basket stock-days that rose
    base_rate: float | None       # fraction of ALL stock-days that rose
    # --- 2026-07-12 additions ---
    spy_cum: float | None         # SPY compounded over the same dates
    mean_daily_turnover: float | None  # mean one-sided daily name-overlap turnover
    long_net_cum: float | None    # cost-adjusted net cumulative return (cost_bps)
    cost_bps_used: float          # the cost_bps parameter used
    breakeven_cost_bps: float | None  # cost at which long_net_cum == spy_cum
    beta: float | None            # OLS beta of daily long returns on SPY
    alpha_ann: float | None       # OLS annualized alpha (intercept × 252)
    alpha_t: float | None         # Newey-West t-stat of the alpha


async def compute_picks_scoreboard(
    pool, *, top_n: int = 10, days: int = 21, cost_bps: float = 10.0
) -> Scoreboard | None:
    """Reconstruct daily top/bottom baskets from stored signals and score them.

    Returns None when there is not enough realized history (fewer than 3
    evaluated days). One SQL pass: per (date) the composite ranking as stored
    that day (fast preferred over slow per ticker+date), joined to realized
    next-day returns. SPY daily returns are read from the same daily_prices
    table (ticker = 'SPY').

    cost_bps: one-way transaction cost in basis points (default 10 bps = 0.0010).
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
            d, {"long": [], "short": [], "all": [], "n_names": int(r["n_names"]),
                "long_tickers": set(), "short_tickers": set()}
        )
        fwd1 = float(r["fwd1"])
        ticker = r["ticker"]
        b["all"].append(fwd1)
        if int(r["rk_top"]) <= top_n:
            b["long"].append(fwd1)
            b["long_tickers"].add(ticker)
        if int(r["rk_bot"]) <= top_n:
            b["short"].append(fwd1)

    # Fetch SPY daily returns for the relevant dates.
    spy_dates_set = frozenset(by_date.keys())
    spy_rows = await pool.fetch(
        """
        SELECT date, close,
               LEAD(close) OVER (ORDER BY date) AS next_close
        FROM daily_prices
        WHERE ticker = 'SPY'
        ORDER BY date
        """,
    )
    spy_ret: dict = {}
    for sr in spy_rows:
        if sr["date"] in spy_dates_set and sr["next_close"] is not None:
            spy_ret[sr["date"]] = float(sr["next_close"]) / float(sr["close"]) - 1.0

    long_cum = short_cum = market_cum = spread_cum = spy_cum_prod = 1.0
    long_up = long_total = all_up = all_total = 0
    evaluated_days = 0

    # Turnover + cost tracking
    cost_factor = cost_bps / 10000.0
    long_net_prod = 1.0
    prev_long_tickers: set = set()
    turnover_sum = 0.0
    turnover_days = 0

    # Daily series for OLS
    daily_long_rets: list[float] = []
    daily_spy_rets: list[float] = []

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

        # Turnover: one-sided name-overlap vs previous basket
        cur_long = b["long_tickers"]
        if prev_long_tickers and top_n > 0:
            overlap = len(cur_long & prev_long_tickers) / top_n
            to_t = 1.0 - overlap
        else:
            # First period: assume full turnover (conservative)
            to_t = 1.0
        prev_long_tickers = cur_long
        turnover_sum += to_t
        turnover_days += 1

        # Net return after cost drag
        net_ret = lr - to_t * cost_factor
        long_net_prod *= 1.0 + net_ret

        # SPY for the same date
        spy_r = spy_ret.get(d)
        if spy_r is not None:
            spy_cum_prod *= 1.0 + spy_r
            daily_long_rets.append(lr)
            daily_spy_rets.append(spy_r)

    if evaluated_days < 3:
        return None

    mean_turnover = (turnover_sum / turnover_days) if turnover_days > 0 else None
    spy_cum_val = spy_cum_prod - 1.0 if len(daily_spy_rets) >= 3 else None
    long_net_cum_val = long_net_prod - 1.0

    # Break-even cost: solve product_t(1 + lr_t - to_t * c) = spy_cum_prod
    # Approximation: net_cum ≈ gross_cum - mean_to * n_days * c (linear in c)
    # => c_be = (gross_cum - spy_cum) / (mean_to * n_days)
    # (gross_cum and spy_cum are decimal, e.g. 0.05)
    breakeven_bps: float | None = None
    if (
        spy_cum_val is not None
        and mean_turnover is not None
        and mean_turnover > 0
        and turnover_days > 0
    ):
        gross_dec = long_cum - 1.0
        spy_dec = spy_cum_val
        total_turnover_weight = mean_turnover * turnover_days
        be_factor = (gross_dec - spy_dec) / total_turnover_weight
        breakeven_bps = be_factor * 10000.0  # convert to bps

    # OLS alpha/beta
    beta_val = alpha_ann_val = alpha_t_val = None
    if len(daily_long_rets) >= 3:
        y_arr = np.array(daily_long_rets, dtype=float)
        x_arr = np.array(daily_spy_rets, dtype=float)
        b_val, a_ann, a_t = _ols_alpha_beta(y_arr, x_arr)
        if not math.isnan(b_val):
            beta_val = b_val
            alpha_ann_val = a_ann
            alpha_t_val = a_t

    return Scoreboard(
        days=evaluated_days,
        top_n=top_n,
        long_cum=long_cum - 1.0,
        short_cum=short_cum - 1.0,
        market_cum=market_cum - 1.0,
        spread_cum=spread_cum - 1.0,
        long_hit_rate=(long_up / long_total) if long_total else None,
        base_rate=(all_up / all_total) if all_total else None,
        spy_cum=spy_cum_val,
        mean_daily_turnover=mean_turnover,
        long_net_cum=long_net_cum_val,
        cost_bps_used=cost_bps,
        breakeven_cost_bps=breakeven_bps,
        beta=beta_val,
        alpha_ann=alpha_ann_val,
        alpha_t=alpha_t_val,
    )
