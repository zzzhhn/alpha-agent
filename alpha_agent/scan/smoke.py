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
    """Synthetic panel populating ALL operands the AST validator accepts.

    Smoke only verifies syntactic + shape correctness (non-all-NaN factor on
    a (T, N) array), so the values themselves don't need to be realistic.
    What matters is that every key in core/factor_ast._ALLOWED_OPERANDS
    has a (T, N) array under it — otherwise an LLM-generated expression
    using a T2 fundamental (e.g. `operating_income`) crashes at
    evaluator's `data[node.id]` lookup with KeyError, surfaced to the
    user as "HTTP 500: Smoke test crashed".
    """
    rng = np.random.default_rng(seed)
    T = lookback + 11

    # ── Core OHLCV (geometric Brownian motion) ──────────────────────
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

    data: dict[str, np.ndarray] = {
        "close": close, "open": open_, "high": high, "low": low,
        "volume": volume, "returns": returns, "vwap": vwap,
    }

    # ── Price/volume metadata (broadcast snapshots) ─────────────────
    cap_per_ticker = rng.lognormal(24.0, 1.5, size=(n_tickers,))   # ~$10B-$1T
    data["cap"] = np.broadcast_to(cap_per_ticker, (T, n_tickers)).copy()
    dollar_vol = close * volume
    data["dollar_volume"] = dollar_vol
    # Multi-window ADV — start with raw dollar_volume; smoke doesn't need
    # accurate rolling means, just non-NaN columns the LLM can reference.
    for window in (5, 10, 20, 60, 120, 180):
        data[f"adv{window}"] = dollar_vol.copy()

    # ── Categorical (broadcast string labels) ───────────────────────
    SECTORS = ["Tech", "Healthcare", "Financial", "Industrials", "Energy"]
    INDUSTRIES = ["Software", "Pharma", "Banking", "Aerospace", "Oil&Gas"]
    EXCHANGES = ["NMS", "NYQ"]
    sector_row = np.array([SECTORS[i % len(SECTORS)] for i in range(n_tickers)])
    industry_row = np.array([INDUSTRIES[i % len(INDUSTRIES)] for i in range(n_tickers)])
    exchange_row = np.array([EXCHANGES[i % len(EXCHANGES)] for i in range(n_tickers)])
    currency_row = np.full(n_tickers, "USD")
    data["sector"] = np.broadcast_to(sector_row, (T, n_tickers)).copy()
    data["industry"] = np.broadcast_to(industry_row, (T, n_tickers)).copy()
    data["subindustry"] = data["industry"]
    data["exchange"] = np.broadcast_to(exchange_row, (T, n_tickers)).copy()
    data["currency"] = np.broadcast_to(currency_row, (T, n_tickers)).copy()

    # ── Fundamentals (per-ticker constants, broadcast across T) ─────
    # Random but stable per ticker — quarterly fundamentals don't move
    # day-to-day, and smoke only needs cross-sectional variation.
    def _fund(scale: float, low: float | None = None) -> np.ndarray:
        sigma = abs(scale) * 0.5
        per_ticker = rng.normal(scale, sigma, size=(n_tickers,))
        if low is not None:
            per_ticker = np.maximum(per_ticker, low)
        return np.broadcast_to(per_ticker, (T, n_tickers)).copy()

    data["revenue"] = _fund(1e10, 1e8)
    data["net_income_adjusted"] = _fund(1e9)
    data["ebitda"] = _fund(2e9)
    data["eps"] = _fund(5.0, 0.1)
    data["gross_profit"] = _fund(4e9, 1e8)
    data["operating_income"] = _fund(2e9)
    data["cost_of_goods_sold"] = _fund(5e9, 1e8)
    data["ebit"] = _fund(2e9)
    data["equity"] = _fund(2e10, 1e8)
    data["assets"] = _fund(5e10, 1e9)
    data["current_assets"] = _fund(1e10, 1e8)
    data["current_liabilities"] = _fund(8e9, 1e8)
    data["long_term_debt"] = _fund(1e10)
    data["short_term_debt"] = _fund(2e9)
    data["cash_and_equivalents"] = _fund(5e9, 1e8)
    data["retained_earnings"] = _fund(1e10)
    data["goodwill"] = _fund(2e9)
    data["free_cash_flow"] = _fund(3e9)
    data["operating_cash_flow"] = _fund(4e9)
    data["investing_cash_flow"] = _fund(-2e9)

    return data


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
