"""Vectorized operator implementations for FactorSpec expressions.

Pure numpy for W2. numba acceleration arrives in W4 when slider-live recompute
demands sub-800ms first-frame (REFACTOR_PLAN.md §4.2). All ts_* ops act on
axis=0 (time). Cross-sectional ops (rank/scale/winsorize) act on axis=1.

Shape convention: (T, N) where T = time, N = cross-section.
NaN semantics: NaN propagates; insufficient-window rows yield NaN.
"""

from __future__ import annotations

import ast
from typing import Callable

import numpy as np

ArrayLike = np.ndarray | float | int


# ── Time-series (axis=0) ────────────────────────────────────────────────────


def _as_2d(arr: np.ndarray) -> np.ndarray:
    return arr if arr.ndim >= 2 else arr.reshape(-1, 1)


def ts_mean(arr: np.ndarray, window: int) -> np.ndarray:
    """Rolling mean along time axis, NaN-safe."""
    if window < 1:
        raise ValueError("window must be >= 1")
    x = np.asarray(arr, dtype=np.float64)
    T = x.shape[0]
    out = np.full_like(x, np.nan)
    if T < window:
        return out
    filled = np.where(np.isnan(x), 0.0, x)
    counts = (~np.isnan(x)).astype(np.float64)
    cum_sum = np.cumsum(filled, axis=0)
    cum_cnt = np.cumsum(counts, axis=0)
    head_sum = np.concatenate(
        [np.zeros_like(cum_sum[:1]), cum_sum[:-window]], axis=0
    )[: T - window + 1]
    head_cnt = np.concatenate(
        [np.zeros_like(cum_cnt[:1]), cum_cnt[:-window]], axis=0
    )[: T - window + 1]
    window_sum = cum_sum[window - 1 :] - head_sum
    window_cnt = cum_cnt[window - 1 :] - head_cnt
    with np.errstate(divide="ignore", invalid="ignore"):
        out[window - 1 :] = np.where(window_cnt > 0, window_sum / window_cnt, np.nan)
    return out


def ts_std(arr: np.ndarray, window: int) -> np.ndarray:
    """Rolling population std (ddof=0)."""
    x = np.asarray(arr, dtype=np.float64)
    m = ts_mean(x, window)
    m2 = ts_mean(x * x, window)
    var = m2 - m * m
    return np.sqrt(np.maximum(var, 0.0))


def ts_zscore(arr: np.ndarray, window: int) -> np.ndarray:
    x = np.asarray(arr, dtype=np.float64)
    m = ts_mean(x, window)
    s = ts_std(x, window)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(s > 0, (x - m) / s, np.nan)


def ts_rank(arr: np.ndarray, window: int) -> np.ndarray:
    """Percentile rank of the latest value within its rolling window."""
    x = np.asarray(arr, dtype=np.float64)
    T = x.shape[0]
    out = np.full_like(x, np.nan)
    for t in range(window - 1, T):
        block = x[t - window + 1 : t + 1]
        last = block[-1]
        valid = ~np.isnan(block)
        count = valid.sum(axis=0)
        less = np.nansum(block < last[None, :], axis=0)
        equal = np.nansum(block == last[None, :], axis=0)
        with np.errstate(divide="ignore", invalid="ignore"):
            out[t] = np.where(count > 0, (less + 0.5 * equal) / count, np.nan)
    return out


def ts_corr(a: np.ndarray, b: np.ndarray, window: int) -> np.ndarray:
    ax = np.asarray(a, dtype=np.float64)
    bx = np.asarray(b, dtype=np.float64)
    ma = ts_mean(ax, window)
    mb = ts_mean(bx, window)
    mab = ts_mean(ax * bx, window)
    sa = ts_std(ax, window)
    sb = ts_std(bx, window)
    cov = mab - ma * mb
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where((sa > 0) & (sb > 0), cov / (sa * sb), np.nan)


# ── Cross-section (axis=1) ──────────────────────────────────────────────────


def rank(arr: np.ndarray) -> np.ndarray:
    """Cross-sectional percentile rank in [0, 1]."""
    x = np.asarray(arr, dtype=np.float64)
    x2 = _as_2d(x)
    out = np.full_like(x2, np.nan)
    for t in range(x2.shape[0]):
        row = x2[t]
        mask = ~np.isnan(row)
        n = int(mask.sum())
        if n == 0:
            continue
        vals = row[mask]
        order = vals.argsort().argsort().astype(np.float64)
        row_out = np.full_like(row, np.nan)
        row_out[mask] = (order + 1.0) / n
        out[t] = row_out
    return out.reshape(x.shape)


def scale(arr: np.ndarray) -> np.ndarray:
    """Cross-sectional demean and normalize to unit L1."""
    x = np.asarray(arr, dtype=np.float64)
    x2 = _as_2d(x)
    out = np.full_like(x2, np.nan)
    for t in range(x2.shape[0]):
        row = x2[t]
        if np.all(np.isnan(row)):
            continue
        centered = row - np.nanmean(row)
        norm = np.nansum(np.abs(centered))
        if norm > 0:
            out[t] = centered / norm
    return out.reshape(x.shape)


def winsorize(arr: np.ndarray, pct: float = 0.01) -> np.ndarray:
    """Cross-sectional winsorization at [pct, 1-pct]."""
    x = np.asarray(arr, dtype=np.float64)
    x2 = _as_2d(x)
    out = np.full_like(x2, np.nan)
    for t in range(x2.shape[0]):
        row = x2[t]
        if np.all(np.isnan(row)):
            continue
        lo, hi = np.nanquantile(row, [pct, 1.0 - pct])
        out[t] = np.clip(row, lo, hi)
    return out.reshape(x.shape)


# ── Elementwise ─────────────────────────────────────────────────────────────


def log(arr: ArrayLike) -> np.ndarray:
    x = np.asarray(arr, dtype=np.float64)
    with np.errstate(invalid="ignore"):
        return np.log(np.where(x > 0, x, np.nan))


def sign(arr: ArrayLike) -> np.ndarray:
    return np.sign(np.asarray(arr, dtype=np.float64))


def add(a: ArrayLike, b: ArrayLike) -> np.ndarray:
    return np.add(np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64))


def sub(a: ArrayLike, b: ArrayLike) -> np.ndarray:
    return np.subtract(np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64))


def mul(a: ArrayLike, b: ArrayLike) -> np.ndarray:
    return np.multiply(np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64))


def div(a: ArrayLike, b: ArrayLike) -> np.ndarray:
    ax = np.asarray(a, dtype=np.float64)
    bx = np.asarray(b, dtype=np.float64)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(bx != 0, np.divide(ax, bx), np.nan)


def pow_(a: ArrayLike, b: ArrayLike) -> np.ndarray:
    return np.power(np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64))


OPS: dict[str, Callable[..., np.ndarray]] = {
    "ts_mean": ts_mean,
    "ts_std": ts_std,
    "ts_zscore": ts_zscore,
    "ts_rank": ts_rank,
    "ts_corr": ts_corr,
    "rank": rank,
    "scale": scale,
    "winsorize": winsorize,
    "log": log,
    "sign": sign,
    "add": add,
    "sub": sub,
    "mul": mul,
    "div": div,
    "pow": pow_,
}


# ── Safe evaluator (AST walker, no eval/exec) ───────────────────────────────


def evaluate(expression: str, data: dict[str, np.ndarray]) -> np.ndarray:
    """Evaluate a pre-AST-validated FactorSpec expression via explicit dispatch.

    The expression has already passed alpha_agent.core.factor_ast.validate_expression,
    but this evaluator re-walks the AST and dispatches through OPS explicitly.
    No eval/exec — every node type is matched and rejected on mismatch.
    """
    tree = ast.parse(expression, mode="eval")
    return _eval_node(tree.body, data)


def _eval_node(node: ast.AST, data: dict[str, np.ndarray]) -> np.ndarray | float | int:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return node.value
        raise ValueError(f"non-numeric constant {node.value!r}")
    if isinstance(node, ast.Name):
        if node.id in data:
            return data[node.id]
        raise KeyError(f"operand {node.id!r} missing from data")
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise ValueError("only direct function calls supported")
        fn = OPS.get(node.func.id)
        if fn is None:
            raise ValueError(f"unknown operator {node.func.id!r}")
        args = [_eval_node(a, data) for a in node.args]
        return fn(*args)
    raise ValueError(f"unsupported AST node {type(node).__name__}")
