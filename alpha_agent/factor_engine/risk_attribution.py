"""Market α / β decomposition (T3.B of v4).

Answers the most fundamental question for any factor: "is this real alpha or
just leveraged market beta?" A long-only factor with Sharpe 2.0 in a bull
market might trace 100% of its return to β = 0.8 vs SPY — i.e., zero true
alpha, just a market-correlated bet that happened to be in the right
direction.

The regression: daily_strategy_return = α + β × daily_benchmark_return + ε

Outputs:
  alpha_daily     — intercept (mean daily excess return after β-adjustment)
  alpha_annualized — alpha_daily × 252 (canonical reporting unit)
  beta_market     — slope (sensitivity to benchmark)
  alpha_t_stat    — alpha / SE(alpha); test that alpha ≠ 0
  alpha_pvalue    — two-sided p-value via normal approximation (n>30 typically)
  r_squared       — fraction of strategy variance explained by benchmark

Interpretation:
  * |α_annualized| > 0 AND alpha_pvalue < 0.05 → statistically meaningful alpha
  * High r_squared (> 0.5) → strategy is mostly tracking benchmark
  * β > 1 → leveraged-long; β < 0 → contrarian; β ≈ 0 → market-neutral
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class MarketDecomposition:
    """Output of `decompose_alpha_beta()`. All fields default to 0 for empty
    input; downstream consumers should check `n_obs` to detect."""
    alpha_daily: float = 0.0
    alpha_annualized: float = 0.0
    beta_market: float = 0.0
    alpha_t_stat: float = 0.0
    alpha_pvalue: float = 1.0
    r_squared: float = 0.0
    n_obs: int = 0


def decompose_alpha_beta(
    strategy_ret: np.ndarray,
    benchmark_ret: np.ndarray,
) -> MarketDecomposition:
    """Run OLS y = α + β·x + ε on aligned daily returns.

    Args:
        strategy_ret: 1D array of daily strategy returns. NaN-safe.
        benchmark_ret: 1D array of daily benchmark returns (typically SPY).
                       Must align with strategy_ret index.

    Returns:
        MarketDecomposition. All zeros if fewer than 30 paired non-NaN
        observations or if benchmark variance is degenerate (constant).

    Implementation note: closed-form OLS using sample sums; no scipy. SE(α)
    derived from residual variance under the standard linear-model
    assumption (homoscedastic ε). For our use case (daily returns, n in
    [50, 250]) the t-distribution converges to normal so we use the normal
    CDF for p-values to stay scipy-free.
    """
    y = np.asarray(strategy_ret, dtype=np.float64)
    x = np.asarray(benchmark_ret, dtype=np.float64)
    if y.shape != x.shape:
        # Truncate to common length from the start (panel head is typically
        # the NaN window for both)
        min_len = min(y.size, x.size)
        y = y[-min_len:]
        x = x[-min_len:]

    mask = ~(np.isnan(y) | np.isnan(x))
    y = y[mask]
    x = x[mask]
    n = y.size
    if n < 30:
        return MarketDecomposition(n_obs=n)

    x_mean = float(x.mean())
    y_mean = float(y.mean())
    var_x = float(((x - x_mean) ** 2).sum())
    if var_x < 1e-20:
        # Constant benchmark — β undefined; fall back to "alpha = mean strategy ret"
        return MarketDecomposition(
            alpha_daily=y_mean,
            alpha_annualized=y_mean * 252.0,
            n_obs=n,
        )

    cov_xy = float(((x - x_mean) * (y - y_mean)).sum())
    beta = cov_xy / var_x
    alpha = y_mean - beta * x_mean

    pred = alpha + beta * x
    resid = y - pred
    rss = float((resid ** 2).sum())
    tss = float(((y - y_mean) ** 2).sum())
    r_squared = 1.0 - rss / tss if tss > 1e-20 else 0.0

    # Standard error of α under homoscedastic OLS
    s2 = rss / (n - 2) if n > 2 else 0.0
    se_alpha_sq = s2 * (1.0 / n + (x_mean ** 2) / var_x)
    se_alpha = math.sqrt(max(se_alpha_sq, 0.0))
    if se_alpha > 1e-20:
        t_stat = alpha / se_alpha
        p_value = math.erfc(abs(t_stat) / math.sqrt(2.0))  # two-sided normal approx
    else:
        t_stat = 0.0
        p_value = 1.0

    return MarketDecomposition(
        alpha_daily=alpha,
        alpha_annualized=alpha * 252.0,
        beta_market=beta,
        alpha_t_stat=t_stat,
        alpha_pvalue=p_value,
        r_squared=r_squared,
        n_obs=n,
    )
