"""Pure-function evaluation kernel reused by backtest + screener.

Why this lives separately from `factor_backtest.py`:
  * `factor_backtest.py` mixes panel I/O, parquet caching, and result
    serialization with the actual numeric pipeline. Anything that wants to
    evaluate a factor cross-sectionally (e.g. /screener — D1 in v3) had to
    drag the whole equity-curve machinery along.
  * Pure functions here take an already-loaded `_Panel`, never touch disk,
    and return raw NumPy arrays. They're cheap to unit test and trivially
    reusable.

Public surface (today):
  build_data_dict(panel)       -> {operand_name: (T, N) array} for eval_factor
  evaluate_factor_full(...)    -> full (T, N) factor values
  evaluate_cross_section(...)  -> {ticker: score} at a chosen row

A future cut will move `run_kernel(panel, spec, params) -> SplitMetrics`
out of factor_backtest.py too. Until then this module is intentionally
small to keep the diff reviewable.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from alpha_agent.scan.vectorized import evaluate as eval_factor
from alpha_agent.scan.vectorized import ts_mean as _ts_mean

if TYPE_CHECKING:
    from alpha_agent.core.types import FactorSpec
    from alpha_agent.factor_engine.factor_backtest import _Panel

# Multi-window dollar-volume averages computed inline at evaluation time so
# they always reflect the active panel rather than a baked snapshot. Mirror
# of factor_backtest._ADV_WINDOWS (kept in sync deliberately — see also
# `feedback_smoke_panel_must_mirror_ast_whitelist.md`).
_ADV_WINDOWS: tuple[int, ...] = (5, 10, 20, 60, 120, 180)


def build_data_dict(panel: "_Panel") -> dict[str, np.ndarray]:
    """Construct the operand → array dict that `eval_factor` consumes.

    Mirrors the v2 panel schema. Keys present here MUST be a superset of
    `core.factor_ast._ALLOWED_OPERANDS` (otherwise translate would AST-pass
    but evaluate-fail). Re-runs cheap; no caching.
    """
    # Trailing 1-day returns: returns[t] = close[t]/close[t-1] - 1. Row 0 is NaN.
    trailing_returns = np.full_like(panel.close, np.nan)
    trailing_returns[1:] = panel.close[1:] / panel.close[:-1] - 1.0

    # VWAP proxy for daily bars: typical price (H+L+C)/3. True VWAP needs
    # intraday data we don't have at this tier.
    vwap_proxy = (panel.high + panel.low + panel.close) / 3.0

    data: dict[str, np.ndarray] = {
        "close": panel.close,
        "open": panel.open_,
        "high": panel.high,
        "low": panel.low,
        "volume": panel.volume,
        "returns": trailing_returns,
        "vwap": vwap_proxy,
    }
    if panel.cap is not None:
        data["cap"] = panel.cap
        dollar_vol = panel.close * panel.volume
        data["dollar_volume"] = dollar_vol
        for w in _ADV_WINDOWS:
            data[f"adv{w}"] = _ts_mean(dollar_vol, w)
    if panel.sector is not None:
        data["sector"] = panel.sector
    if panel.industry is not None:
        data["industry"] = panel.industry
        data.setdefault("subindustry", panel.industry)
    if panel.exchange is not None:
        data["exchange"] = panel.exchange
    if panel.currency is not None:
        data["currency"] = panel.currency
    if panel.fundamentals:
        for fname, farr in panel.fundamentals.items():
            data[fname] = farr
    # Bundle C.3 (v4): expose insider Form 4 operands the same way as
    # fundamentals. None means parquet missing → handled by NaN-fill below.
    if getattr(panel, "insider_form4", None):
        for fname, farr in panel.insider_form4.items():
            data[fname] = farr

    # T1.5a (v4) compat: AST whitelist (`_ALLOWED_OPERANDS`) lists ~22
    # fundamental fields, but a given panel may carry only a subset (e.g. v3
    # SP500 panel from Compustat has no quarterly cash-flow because fundq
    # only stores YTD). Backfill missing fundamentals with NaN arrays so
    # factor expressions still parse and evaluate — they just produce NaN
    # factor values, which surface as zero positions / zero PnL downstream.
    # Better than KeyError at eval time: user sees "factor produced nothing"
    # rather than a stack trace.
    from alpha_agent.core.factor_ast import _ALLOWED_OPERANDS
    _METADATA_OPERANDS = {
        "close", "open", "high", "low", "volume", "returns", "vwap",
        "cap", "sector", "industry", "subindustry", "exchange", "currency",
        "dollar_volume", "adv5", "adv10", "adv20", "adv60", "adv120", "adv180",
    }
    fundamental_operands = _ALLOWED_OPERANDS - _METADATA_OPERANDS
    nan_shape = panel.close.shape
    for op in fundamental_operands:
        if op not in data:
            data[op] = np.full(nan_shape, np.nan, dtype=np.float64)

    return data


def evaluate_factor_full(panel: "_Panel", spec: "FactorSpec") -> np.ndarray:
    """Run a FactorSpec against the panel and return the (T, N) factor values.

    T1.5b (v4): if the panel carries an `is_member` mask, non-member cells in
    the final factor array are NaN'd out so they cannot enter the long/short
    basket and cannot contaminate cross-sectional IC. The mask is applied
    AFTER operator evaluation — per-ticker time-series ops (ts_mean, ts_std,
    etc.) keep using full price history, but the trading decision only sees
    cells where the ticker was an actual SP500 constituent.

    Caveat: cross-sectional ops inside the expression (rank, group_neutralize)
    still see all 98 tickers when computing ranks. For the SP100 panel this
    distorts ranks by ~4% (4 movers out of 98); for full SP500 with delisted
    tickers this matters more and would require row-by-row re-ranking.

    Raises:
        ValueError: factor expression evaluates to an unexpected shape.
        Any exception raised by `eval_factor`: propagated with original type
        (FactorSpecValidationError, KeyError for unknown operand, etc.).
    """
    T, N = panel.close.shape
    data = build_data_dict(panel)
    factor = np.asarray(eval_factor(spec.expression, data), dtype=np.float64)
    if factor.shape != (T, N):
        raise ValueError(
            f"factor expression produced shape {factor.shape}, expected ({T}, {N})"
        )
    if panel.is_member is not None:
        factor = np.where(panel.is_member, factor, np.nan)
    return factor


def spearman_ic(factor_row: np.ndarray, fwd_ret_row: np.ndarray) -> float:
    """Single-day cross-sectional Spearman IC. NaN-safe.

    Returns 0.0 when fewer than 3 valid observations, or the rank-vector
    has zero variance. The result lives in [-1, 1].
    """
    mask = ~(np.isnan(factor_row) | np.isnan(fwd_ret_row))
    if int(mask.sum()) < 3:
        return 0.0
    f = factor_row[mask]
    r = fwd_ret_row[mask]
    f_rank = f.argsort().argsort().astype(np.float64)
    r_rank = r.argsort().argsort().astype(np.float64)
    f_centered = f_rank - f_rank.mean()
    r_centered = r_rank - r_rank.mean()
    denom = float(np.sqrt((f_centered**2).sum() * (r_centered**2).sum()))
    if denom == 0.0:
        return 0.0
    return float((f_centered * r_centered).sum() / denom)


def window_ic(
    factor: np.ndarray,
    fwd_returns: np.ndarray,
    start: int,
    end: int,
) -> float:
    """Mean Spearman IC over rows [start, end). Skips NaN-only rows.

    `factor` and `fwd_returns` are (T, N) aligned arrays. Used by the
    screener's ic-weighted combiner to estimate each factor's recent
    informativeness.
    """
    samples: list[float] = []
    T = factor.shape[0]
    end = min(end, T, fwd_returns.shape[0])
    for t in range(max(0, start), end):
        ic = spearman_ic(factor[t], fwd_returns[t])
        if not np.isnan(ic):
            samples.append(ic)
    return float(np.mean(samples)) if samples else 0.0


def evaluate_cross_section(
    panel: "_Panel",
    spec: "FactorSpec",
    as_of_index: int = -1,
) -> dict[str, float]:
    """Return {ticker: score} for the chosen row of the panel.

    Used by /screener (D1) to rank tickers by a single factor at a single
    point in time. NaN scores are dropped so downstream z-score / rank
    aggregation only sees populated entries.

    Args:
        panel: loaded panel object.
        spec:  validated FactorSpec.
        as_of_index: row to read. Defaults to -1 (most recent).
                     Negative indexing supported.

    Raises:
        IndexError: as_of_index out of range.
    """
    factor = evaluate_factor_full(panel, spec)
    T, N = factor.shape
    # Normalize negative index for clearer error messages
    idx = as_of_index if as_of_index >= 0 else T + as_of_index
    if not 0 <= idx < T:
        raise IndexError(
            f"as_of_index {as_of_index} out of range for panel of length {T}"
        )
    row = factor[idx]
    return {
        panel.tickers[i]: float(row[i])
        for i in range(N)
        if not np.isnan(row[i])
    }
