"""10-day smoke test for a validated FactorSpec.

Purpose: before a freshly-translated FactorSpec reaches the real backtest
(weeks of OHLCV), prove it is numerically executable and produces a non-trivial
signal on synthetic data. Catches shape bugs, divide-by-zero, and broken
operator composition in under 200ms.

Design (REFACTOR_PLAN.md §3.1 step 3):
  - Synthetic panel: N=20 tickers, T = lookback + 11 days of GBM returns
  - Panel covers all 190 B+ operands; operands used by the expression are
    materialized lazily via AST name extraction (faster + leaner than
    allocating 190×T×N arrays every call)
  - Evaluate the factor over the full panel
  - Compute per-day cross-sectional Spearman IC vs 1-day forward return
  - Average the last 10 days' IC -> SmokeResult.ic_spearman

Operand synthesis strategy (B+ expansion, 2026-04-18):
  - PriceVolume: derived from shared GBM (close, open, high, low, vwap, volume,
    returns) or drawn from category-appropriate distributions (adv20 ~ volume).
  - Fundamental: lognormal for dollar amounts, normal around zero for ratios/
    growth (detected by name suffix).
  - Model: standard-normal factor scores around zero.
  - Analyst: lognormal for counts / target prices.
  - Sentiment: uniform in [0, 1].
  - Non-numeric dtypes (Group, Symbol): constant-index broadcast so ts_/arith
    ops no-op rather than crashing — a factor that depends on these will just
    return NaN IC and fail the smoke gate, which is correct.
"""

from __future__ import annotations

import ast
import time
from dataclasses import dataclass

import numpy as np

from alpha_agent.core.brain_registry import OPERANDS, OperandSpec
from alpha_agent.scan.vectorized import evaluate, rank


@dataclass(frozen=True)
class SmokeResult:
    rows_valid: int
    ic_spearman: float
    runtime_ms: float


# Name suffixes that indicate a ratio/percentage rather than a dollar amount.
_RATIO_SUFFIXES = (
    "_growth", "_ratio", "_margin", "_rate", "_yield", "_pct", "_percent",
    "_rank", "_score", "_flag",
)


def _extract_operand_names(expression: str) -> set[str]:
    tree = ast.parse(expression, mode="eval")
    return {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}


def _derive_base_panel(
    rng: np.random.Generator, T: int, n_tickers: int
) -> dict[str, np.ndarray]:
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


def _generate_operand(
    name: str, spec: OperandSpec, rng: np.random.Generator, T: int, n_tickers: int
) -> np.ndarray:
    shape = (T, n_tickers)

    # Non-numeric identifier columns: constant per column so numeric ops yield NaN/0.
    if spec.dtype in ("Group", "Symbol"):
        return np.zeros(shape, dtype=np.float64)

    is_ratio = any(name.endswith(suffix) for suffix in _RATIO_SUFFIXES)

    if spec.category == "PriceVolume":
        # adv20 / cap etc: lognormal around volume scale
        return rng.lognormal(10.0, 0.5, size=shape)

    if spec.category == "Fundamental":
        if is_ratio:
            return rng.normal(0.05, 0.10, size=shape)
        # Dollar amounts: lognormal (median ~ $1M, wide spread)
        return rng.lognormal(14.0, 1.5, size=shape)

    if spec.category == "Model":
        # Factor/risk scores: standard normal, smoothed to look like time series
        raw = rng.normal(0.0, 1.0, size=shape)
        return _smooth_axis0(raw, halflife=5)

    if spec.category == "Analyst":
        if is_ratio:
            return rng.uniform(0.0, 1.0, size=shape)
        return rng.lognormal(2.5, 0.5, size=shape)

    if spec.category == "Sentiment":
        return rng.uniform(0.0, 1.0, size=shape)

    # Unknown category — zero panel. Factors that depend on it smoke-test to NaN IC.
    return np.zeros(shape, dtype=np.float64)


def _smooth_axis0(x: np.ndarray, halflife: int) -> np.ndarray:
    """Exponential smoothing along axis 0 — makes Model factors look persistent."""
    alpha = 1.0 - 0.5 ** (1.0 / halflife)
    out = np.empty_like(x)
    out[0] = x[0]
    for t in range(1, x.shape[0]):
        out[t] = alpha * x[t] + (1 - alpha) * out[t - 1]
    return out


def _synthetic_panel(
    expression: str, lookback: int, n_tickers: int, seed: int
) -> dict[str, np.ndarray]:
    """Build only the operand panels the expression actually references."""
    rng = np.random.default_rng(seed)
    T = lookback + 11
    panel = _derive_base_panel(rng, T, n_tickers)

    referenced = _extract_operand_names(expression) & set(OPERANDS)
    for name in sorted(referenced):  # sorted for deterministic seeding
        if name in panel:
            continue
        panel[name] = _generate_operand(name, OPERANDS[name], rng, T, n_tickers)
    return panel


def smoke_test(expression: str, lookback: int, seed: int = 42) -> SmokeResult:
    """Run the 10-day Spearman-IC smoke check for an AST-validated expression."""
    n_tickers = 20
    data = _synthetic_panel(expression, lookback, n_tickers, seed)
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
