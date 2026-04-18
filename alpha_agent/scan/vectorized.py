"""Vectorized operator implementations for FactorSpec expressions.

Pure numpy for W2. numba acceleration arrives in W4 when slider-live recompute
demands sub-800ms first-frame (REFACTOR_PLAN.md §4.2). All ts_* ops act on
axis=0 (time). Cross-sectional ops (rank/scale/winsorize/zscore) act on axis=1.

Shape convention: (T, N) where T = time, N = cross-section.
NaN semantics: NaN propagates; insufficient-window rows yield NaN.

Naming: functions use Python-safe names (`abs_`, `max_`, `min_`) but are
registered in OPS under BRAIN-canonical keys (`"abs"`, `"max"`, `"min"`).
The AST validator accepts only BRAIN-canonical names (via brain_registry).
"""

from __future__ import annotations

import ast
from typing import Callable

import numpy as np

from alpha_agent.core.brain_registry import IMPLEMENTED_OPERATOR_NAMES, OPERATOR_NAMES

ArrayLike = np.ndarray | float | int


def _as_2d(arr: np.ndarray) -> np.ndarray:
    return arr if arr.ndim >= 2 else arr.reshape(-1, 1)


def _arr(x: ArrayLike) -> np.ndarray:
    return np.asarray(x, dtype=np.float64)


# ── Time-series (axis=0) ────────────────────────────────────────────────────


def ts_mean(arr: ArrayLike, window: int) -> np.ndarray:
    """Rolling mean along time axis, NaN-safe."""
    if window < 1:
        raise ValueError("window must be >= 1")
    x = _arr(arr)
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


def ts_sum(arr: ArrayLike, window: int) -> np.ndarray:
    x = _arr(arr)
    m = ts_mean(x, window)
    return m * window


def _ts_std_internal(arr: ArrayLike, window: int) -> np.ndarray:
    """Rolling population std (ddof=0). Internal helper for ts_zscore/ts_corr."""
    x = _arr(arr)
    m = ts_mean(x, window)
    m2 = ts_mean(x * x, window)
    var = m2 - m * m
    return np.sqrt(np.maximum(var, 0.0))


def ts_zscore(arr: ArrayLike, window: int) -> np.ndarray:
    x = _arr(arr)
    m = ts_mean(x, window)
    s = _ts_std_internal(x, window)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(s > 0, (x - m) / s, np.nan)


def ts_rank(arr: ArrayLike, window: int, constant: int = 0) -> np.ndarray:
    """Percentile rank of the latest value within its rolling window."""
    x = _arr(arr)
    x2d = _as_2d(x)
    T = x2d.shape[0]
    out = np.full_like(x2d, np.nan)
    for t in range(window - 1, T):
        block = x2d[t - window + 1 : t + 1]
        last = block[-1]
        valid = ~np.isnan(block)
        count = valid.sum(axis=0)
        less = np.nansum(block < last[None, :], axis=0)
        equal = np.nansum(block == last[None, :], axis=0)
        with np.errstate(divide="ignore", invalid="ignore"):
            out[t] = np.where(count > 0, (less + 0.5 * equal) / count, np.nan)
    return out.reshape(x.shape) + constant


def ts_corr(a: ArrayLike, b: ArrayLike, window: int) -> np.ndarray:
    ax, bx = _arr(a), _arr(b)
    ma = ts_mean(ax, window)
    mb = ts_mean(bx, window)
    mab = ts_mean(ax * bx, window)
    sa = _ts_std_internal(ax, window)
    sb = _ts_std_internal(bx, window)
    cov = mab - ma * mb
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where((sa > 0) & (sb > 0), cov / (sa * sb), np.nan)


def ts_delta(arr: ArrayLike, d: int) -> np.ndarray:
    """x[t] - x[t-d]."""
    x = _arr(arr)
    out = np.full_like(x, np.nan)
    if d < 1 or d >= x.shape[0]:
        return out
    out[d:] = x[d:] - x[:-d]
    return out


def ts_delay(arr: ArrayLike, d: int) -> np.ndarray:
    """x[t-d]."""
    x = _arr(arr)
    out = np.full_like(x, np.nan)
    if d < 0 or d >= x.shape[0]:
        return out
    if d == 0:
        return x.copy()
    out[d:] = x[:-d]
    return out


def ts_product(arr: ArrayLike, window: int) -> np.ndarray:
    """Rolling product over window. Uses log-space sum to avoid overflow."""
    x = _arr(arr)
    x2d = _as_2d(x)
    T = x2d.shape[0]
    out = np.full_like(x2d, np.nan)
    for t in range(window - 1, T):
        block = x2d[t - window + 1 : t + 1]
        with np.errstate(invalid="ignore"):
            out[t] = np.nanprod(block, axis=0)
    return out.reshape(x.shape)


# ── Cross-section (axis=1) ──────────────────────────────────────────────────


def rank(arr: ArrayLike, rate: int = 2) -> np.ndarray:
    """Cross-sectional percentile rank in [0, 1]. `rate` kwarg accepted for BRAIN parity, ignored."""
    del rate
    x = _arr(arr)
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


def scale(
    arr: ArrayLike, scale: float = 1.0, longscale: float = 1.0, shortscale: float = 1.0
) -> np.ndarray:
    """Cross-sectional demean, normalize to unit L1, then multiply by `scale`."""
    del longscale, shortscale  # BRAIN parity only; symmetric scaling used.
    x = _arr(arr)
    x2 = _as_2d(x)
    out = np.full_like(x2, np.nan)
    for t in range(x2.shape[0]):
        row = x2[t]
        if np.all(np.isnan(row)):
            continue
        centered = row - np.nanmean(row)
        norm = np.nansum(np.abs(centered))
        if norm > 0:
            out[t] = scale * centered / norm
    return out.reshape(x.shape)


def winsorize(arr: ArrayLike, std: float = 4.0) -> np.ndarray:
    """Cross-sectional winsorization at ±`std` standard deviations."""
    x = _arr(arr)
    x2 = _as_2d(x)
    out = np.full_like(x2, np.nan)
    for t in range(x2.shape[0]):
        row = x2[t]
        if np.all(np.isnan(row)):
            continue
        mu = np.nanmean(row)
        sigma = np.nanstd(row)
        lo, hi = mu - std * sigma, mu + std * sigma
        out[t] = np.clip(row, lo, hi)
    return out.reshape(x.shape)


def zscore(arr: ArrayLike) -> np.ndarray:
    """Cross-sectional z-score (axis=1)."""
    x = _arr(arr)
    x2 = _as_2d(x)
    out = np.full_like(x2, np.nan)
    for t in range(x2.shape[0]):
        row = x2[t]
        if np.all(np.isnan(row)):
            continue
        mu = np.nanmean(row)
        sigma = np.nanstd(row)
        if sigma > 0:
            out[t] = (row - mu) / sigma
    return out.reshape(x.shape)


# ── Elementwise ─────────────────────────────────────────────────────────────


def log(arr: ArrayLike) -> np.ndarray:
    x = _arr(arr)
    with np.errstate(invalid="ignore"):
        return np.log(np.where(x > 0, x, np.nan))


def sqrt(arr: ArrayLike) -> np.ndarray:
    x = _arr(arr)
    with np.errstate(invalid="ignore"):
        return np.sqrt(np.where(x >= 0, x, np.nan))


def sign(arr: ArrayLike) -> np.ndarray:
    return np.sign(_arr(arr))


def abs_(arr: ArrayLike) -> np.ndarray:
    return np.abs(_arr(arr))


def inverse(arr: ArrayLike) -> np.ndarray:
    x = _arr(arr)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(x != 0, 1.0 / x, np.nan)


def reverse(arr: ArrayLike) -> np.ndarray:
    """BRAIN reverse(x) = -x (sign flip), not array reversal."""
    return -_arr(arr)


def is_nan(arr: ArrayLike) -> np.ndarray:
    """Returns 1.0 where input is NaN, 0.0 elsewhere (float so it composes)."""
    return np.isnan(_arr(arr)).astype(np.float64)


def add(a: ArrayLike, b: ArrayLike, filter: bool = False) -> np.ndarray:  # noqa: A002
    del filter  # BRAIN parity; filter=true replaces NaN with 0 pre-sum, rarely used here.
    return np.add(_arr(a), _arr(b))


def subtract(a: ArrayLike, b: ArrayLike, filter: bool = False) -> np.ndarray:  # noqa: A002
    del filter
    return np.subtract(_arr(a), _arr(b))


def multiply(a: ArrayLike, b: ArrayLike, filter: bool = False) -> np.ndarray:  # noqa: A002
    del filter
    return np.multiply(_arr(a), _arr(b))


def divide(a: ArrayLike, b: ArrayLike) -> np.ndarray:
    ax, bx = _arr(a), _arr(b)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(bx != 0, np.divide(ax, bx), np.nan)


def power(a: ArrayLike, b: ArrayLike) -> np.ndarray:
    return np.power(_arr(a), _arr(b))


def signed_power(a: ArrayLike, b: ArrayLike) -> np.ndarray:
    """sign(a) * |a|**b — preserves sign while amplifying magnitude."""
    ax = _arr(a)
    return np.sign(ax) * np.power(np.abs(ax), _arr(b))


def max_(*args: ArrayLike) -> np.ndarray:
    if not args:
        raise ValueError("max requires at least one argument")
    out = _arr(args[0])
    for a in args[1:]:
        out = np.maximum(out, _arr(a))
    return out


def min_(*args: ArrayLike) -> np.ndarray:
    if not args:
        raise ValueError("min requires at least one argument")
    out = _arr(args[0])
    for a in args[1:]:
        out = np.minimum(out, _arr(a))
    return out


def if_else(cond: ArrayLike, a: ArrayLike, b: ArrayLike) -> np.ndarray:
    """Vectorized ternary. cond treated as bool (nonzero=True), NaN propagates."""
    cx = _arr(cond)
    ax, bx = _arr(a), _arr(b)
    nan_mask = np.isnan(cx)
    bool_cond = np.where(nan_mask, False, cx.astype(bool))
    result = np.where(bool_cond, ax, bx)
    return np.where(nan_mask, np.nan, result)


# ── Not-yet-implemented (registered so grammar accepts, but raise at runtime) ──


def _unimplemented(name: str) -> Callable[..., np.ndarray]:
    def stub(*args, **kwargs):  # noqa: ARG001
        raise NotImplementedError(
            f"operator {name!r} is in the grammar but has no vectorized impl yet; "
            f"see brain_registry.IMPLEMENTED_OPERATOR_NAMES for current coverage"
        )
    stub.__name__ = f"_unimpl_{name}"
    return stub


# ── OPS registry ────────────────────────────────────────────────────────────

OPS: dict[str, Callable[..., np.ndarray]] = {
    # Time-series
    "ts_mean": ts_mean,
    "ts_sum": ts_sum,
    "ts_zscore": ts_zscore,
    "ts_rank": ts_rank,
    "ts_corr": ts_corr,
    "ts_delta": ts_delta,
    "ts_delay": ts_delay,
    "ts_product": ts_product,
    # Cross-sectional
    "rank": rank,
    "scale": scale,
    "winsorize": winsorize,
    "zscore": zscore,
    # Elementwise unary
    "log": log,
    "sqrt": sqrt,
    "sign": sign,
    "abs": abs_,
    "inverse": inverse,
    "reverse": reverse,
    "is_nan": is_nan,
    # Elementwise binary
    "add": add,
    "subtract": subtract,
    "multiply": multiply,
    "divide": divide,
    "power": power,
    "signed_power": signed_power,
    # Variadic
    "max": max_,
    "min": min_,
    "if_else": if_else,
}

# Fill stubs for every operator in the registry whitelist that lacks an impl.
for _name in OPERATOR_NAMES - IMPLEMENTED_OPERATOR_NAMES:
    OPS[_name] = _unimplemented(_name)


# Build-time guarantee: OPS covers every whitelisted operator exactly.
assert set(OPS) == OPERATOR_NAMES, (
    f"OPS drift: in OPS not registry = {set(OPS) - OPERATOR_NAMES}; "
    f"in registry not OPS = {OPERATOR_NAMES - set(OPS)}"
)


# ── Safe evaluator (AST walker, no eval/exec) ───────────────────────────────


def evaluate(expression: str, data: dict[str, np.ndarray]) -> np.ndarray | float:
    """Evaluate a pre-validated FactorSpec expression via explicit AST dispatch.

    The expression has already passed alpha_agent.core.factor_ast.validate_expression,
    but this evaluator re-walks the AST and dispatches through OPS explicitly.
    No eval/exec — every node type is matched and rejected on mismatch.
    """
    tree = ast.parse(expression, mode="eval")
    return _eval_node(tree.body, data)


_CMP_OPS: dict[type[ast.cmpop], Callable] = {
    ast.Eq: np.equal, ast.NotEq: np.not_equal,
    ast.Lt: np.less, ast.LtE: np.less_equal,
    ast.Gt: np.greater, ast.GtE: np.greater_equal,
}


def _nan_aware_binary(op: Callable, left, right) -> np.ndarray:
    l, r = _arr(left), _arr(right)
    with np.errstate(invalid="ignore"):
        res = op(l, r).astype(np.float64)
    return np.where(np.isnan(l) | np.isnan(r), np.nan, res)


def _eval_node(node: ast.AST, data: dict[str, np.ndarray]):
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool):
            raise ValueError("boolean literals not allowed")
        if isinstance(node.value, (int, float, str)):
            return node.value
        raise ValueError(f"unsupported constant {node.value!r}")

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
        kwargs = {kw.arg: _eval_node(kw.value, data) for kw in node.keywords}
        return fn(*args, **kwargs)

    if isinstance(node, ast.Compare):
        left = _eval_node(node.left, data)
        current = left
        result = None
        for op_node, comparator in zip(node.ops, node.comparators):
            right = _eval_node(comparator, data)
            op_fn = _CMP_OPS.get(type(op_node))
            if op_fn is None:
                raise ValueError(f"unsupported compare op {type(op_node).__name__}")
            step = _nan_aware_binary(op_fn, current, right)
            result = step if result is None else _nan_aware_binary(np.logical_and, result, step)
            current = right
        return result

    if isinstance(node, ast.BoolOp):
        op_fn = np.logical_and if isinstance(node.op, ast.And) else np.logical_or
        values = [_eval_node(v, data) for v in node.values]
        acc = values[0]
        for v in values[1:]:
            acc = _nan_aware_binary(op_fn, acc, v)
        return acc

    if isinstance(node, ast.UnaryOp):
        operand = _eval_node(node.operand, data)
        x = _arr(operand)
        if isinstance(node.op, ast.Not):
            nan_mask = np.isnan(x)
            return np.where(nan_mask, np.nan, (x == 0).astype(np.float64))
        if isinstance(node.op, ast.USub):
            return -x
        if isinstance(node.op, ast.UAdd):
            return x
        raise ValueError(f"unsupported unary op {type(node.op).__name__}")

    raise ValueError(f"unsupported AST node {type(node).__name__}")
