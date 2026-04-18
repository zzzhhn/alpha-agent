"""10-day smoke test for a validated FactorSpec.

Purpose: before a freshly-translated FactorSpec reaches the real backtest
(weeks of OHLCV), prove it is numerically executable and produces a non-trivial
signal on synthetic data. Catches shape bugs, divide-by-zero, and broken
operator composition in under 200ms.

Design (REFACTOR_PLAN.md §3.1 step 3):
  - Synthetic panel: N=20 tickers, T = lookback + 11 days of GBM returns
  - Evaluate the factor over the full panel
  - Compute per-day cross-sectional Spearman IC vs 1-day forward return
  - Average the last 10 days' IC -> SmokeResult.ic_spearman
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

from alpha_agent.scan.vectorized import evaluate, rank


@dataclass(frozen=True)
class SmokeResult:
    rows_valid: int
    ic_spearman: float
    runtime_ms: float


def _synthetic_panel(lookback: int, n_tickers: int, seed: int) -> dict[str, np.ndarray]:
    """Geometric-Brownian-motion OHLCV panel for smoke testing."""
    rng = np.random.default_rng(seed)
    T = lookback + 11
    daily_ret = rng.normal(0.0, 0.02, size=(T, n_tickers))
    close = 100.0 * np.exp(np.cumsum(daily_ret, axis=0))
    high = close * (1.0 + np.abs(rng.normal(0, 0.01, size=(T, n_tickers))))
    low = close * (1.0 - np.abs(rng.normal(0, 0.01, size=(T, n_tickers))))
    open_ = close * (1.0 + rng.normal(0, 0.005, size=(T, n_tickers)))
    volume = rng.lognormal(10.0, 0.5, size=(T, n_tickers))
    returns = np.vstack(
        [np.full((1, n_tickers), np.nan), np.diff(np.log(close), axis=0)]
    )
    vwap = (high + low + close) / 3.0
    return {
        "close": close,
        "open": open_,
        "high": high,
        "low": low,
        "volume": volume,
        "returns": returns,
        "vwap": vwap,
    }


def smoke_test(expression: str, lookback: int, seed: int = 42) -> SmokeResult:
    """Run the 10-day Spearman-IC smoke check for an AST-validated expression."""
    n_tickers = 20
    data = _synthetic_panel(lookback, n_tickers, seed)
    close = data["close"]

    start = time.perf_counter()
    factor = evaluate(expression, data)
    runtime_ms = (time.perf_counter() - start) * 1000.0

    factor = np.asarray(factor, dtype=np.float64)
    if factor.ndim == 1:
        factor = factor.reshape(-1, 1)

    fwd_ret = np.vstack(
        [np.diff(np.log(close), axis=0), np.full((1, close.shape[1]), np.nan)]
    )

    tail = 10
    if factor.shape[0] < tail + 1:
        return SmokeResult(rows_valid=0, ic_spearman=float("nan"), runtime_ms=runtime_ms)

    factor_tail = factor[-(tail + 1) : -1]
    fwd_tail = fwd_ret[-(tail + 1) : -1]
    factor_rank = rank(factor_tail)
    fwd_rank = rank(fwd_tail)

    valid = ~(np.isnan(factor_rank) | np.isnan(fwd_rank))
    daily_ics: list[float] = []
    for t in range(factor_rank.shape[0]):
        m = valid[t]
        if int(m.sum()) < 3:
            continue
        x = factor_rank[t, m]
        y = fwd_rank[t, m]
        if x.std() == 0 or y.std() == 0:
            continue
        corr = float(np.corrcoef(x, y)[0, 1])
        if np.isfinite(corr):
            daily_ics.append(corr)

    ic = float(np.mean(daily_ics)) if daily_ics else float("nan")
    return SmokeResult(
        rows_valid=int(valid.sum()),
        ic_spearman=ic,
        runtime_ms=float(runtime_ms),
    )
