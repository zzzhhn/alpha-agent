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


# ── Arithmetic (additions) ──────────────────────────────────────────────────


def abs_(arr: ArrayLike) -> np.ndarray:
    return np.abs(np.asarray(arr, dtype=np.float64))


def inverse(arr: ArrayLike) -> np.ndarray:
    x = np.asarray(arr, dtype=np.float64)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(x != 0, 1.0 / x, np.nan)


def sqrt(arr: ArrayLike) -> np.ndarray:
    x = np.asarray(arr, dtype=np.float64)
    return np.sqrt(np.where(x >= 0, x, np.nan))


def signed_power(a: ArrayLike, b: ArrayLike) -> np.ndarray:
    """sign(x) * |x|^y — preserves sign through fractional exponents."""
    ax = np.asarray(a, dtype=np.float64)
    bx = np.asarray(b, dtype=np.float64)
    return np.sign(ax) * np.power(np.abs(ax), bx)


def max_(a: ArrayLike, b: ArrayLike) -> np.ndarray:
    """Element-wise maximum of two arrays (NaN propagates)."""
    return np.maximum(
        np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    )


def min_(a: ArrayLike, b: ArrayLike) -> np.ndarray:
    return np.minimum(
        np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    )


def reverse(arr: ArrayLike) -> np.ndarray:
    return -np.asarray(arr, dtype=np.float64)


def densify(arr: ArrayLike) -> np.ndarray:
    """Replace NaN with 0 — used to convert sparse signals to dense ones."""
    x = np.asarray(arr, dtype=np.float64)
    return np.where(np.isnan(x), 0.0, x)


# ── Logical (returns float 0/1, NaN on undefined) ───────────────────────────


def _bool_to_float(arr: np.ndarray) -> np.ndarray:
    return arr.astype(np.float64)


def is_nan(arr: ArrayLike) -> np.ndarray:
    return _bool_to_float(np.isnan(np.asarray(arr, dtype=np.float64)))


def if_else(cond: ArrayLike, t: ArrayLike, f: ArrayLike) -> np.ndarray:
    """Ternary: when cond is truthy → t, else f. NaN cond → NaN output."""
    c = np.asarray(cond, dtype=np.float64)
    tx = np.asarray(t, dtype=np.float64)
    fx = np.asarray(f, dtype=np.float64)
    out = np.where(c > 0, tx, fx)
    return np.where(np.isnan(c), np.nan, out)


def and_(a: ArrayLike, b: ArrayLike) -> np.ndarray:
    ax = np.asarray(a, dtype=np.float64)
    bx = np.asarray(b, dtype=np.float64)
    return _bool_to_float((ax > 0) & (bx > 0))


def or_(a: ArrayLike, b: ArrayLike) -> np.ndarray:
    ax = np.asarray(a, dtype=np.float64)
    bx = np.asarray(b, dtype=np.float64)
    return _bool_to_float((ax > 0) | (bx > 0))


def not_(arr: ArrayLike) -> np.ndarray:
    x = np.asarray(arr, dtype=np.float64)
    return _bool_to_float(~(x > 0))


def equal(a: ArrayLike, b: ArrayLike) -> np.ndarray:
    return _bool_to_float(np.equal(
        np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    ))


def not_equal(a: ArrayLike, b: ArrayLike) -> np.ndarray:
    return _bool_to_float(np.not_equal(
        np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    ))


def less(a: ArrayLike, b: ArrayLike) -> np.ndarray:
    return _bool_to_float(np.less(
        np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    ))


def greater(a: ArrayLike, b: ArrayLike) -> np.ndarray:
    return _bool_to_float(np.greater(
        np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    ))


def less_equal(a: ArrayLike, b: ArrayLike) -> np.ndarray:
    return _bool_to_float(np.less_equal(
        np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    ))


def greater_equal(a: ArrayLike, b: ArrayLike) -> np.ndarray:
    return _bool_to_float(np.greater_equal(
        np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    ))


# ── Time-series (additions, axis=0) ─────────────────────────────────────────


def ts_delay(arr: np.ndarray, d: int) -> np.ndarray:
    """Shift values d periods forward (i.e., x[t-d] at time t)."""
    x = np.asarray(arr, dtype=np.float64)
    out = np.full_like(x, np.nan)
    if d <= 0:
        return x.copy()
    if d >= x.shape[0]:
        return out
    out[d:] = x[:-d]
    return out


def ts_delta(arr: np.ndarray, d: int) -> np.ndarray:
    """x[t] - x[t-d]."""
    return np.asarray(arr, dtype=np.float64) - ts_delay(arr, d)


def ts_sum(arr: np.ndarray, window: int) -> np.ndarray:
    """Rolling sum (NaN treated as 0 for the sum, but propagates if all-NaN)."""
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
    out[window - 1 :] = np.where(window_cnt > 0, window_sum, np.nan)
    return out


def ts_product(arr: np.ndarray, window: int) -> np.ndarray:
    """Rolling product over `window` periods (log-space for numerical stability)."""
    x = np.asarray(arr, dtype=np.float64)
    T = x.shape[0]
    out = np.full_like(x, np.nan)
    if window < 1 or T < window:
        return out
    for t in range(window - 1, T):
        block = x[t - window + 1 : t + 1]
        valid = ~np.isnan(block)
        # If any element NaN, treat product as NaN (strict)
        all_valid = valid.all(axis=0)
        prod = np.prod(np.where(np.isnan(block), 1.0, block), axis=0)
        out[t] = np.where(all_valid, prod, np.nan)
    return out


def ts_min(arr: np.ndarray, window: int) -> np.ndarray:
    x = np.asarray(arr, dtype=np.float64)
    T = x.shape[0]
    out = np.full_like(x, np.nan)
    if window < 1 or T < window:
        return out
    for t in range(window - 1, T):
        block = x[t - window + 1 : t + 1]
        out[t] = np.nanmin(
            np.where(np.all(np.isnan(block), axis=0), np.nan, block), axis=0
        )
    return out


def ts_max(arr: np.ndarray, window: int) -> np.ndarray:
    x = np.asarray(arr, dtype=np.float64)
    T = x.shape[0]
    out = np.full_like(x, np.nan)
    if window < 1 or T < window:
        return out
    for t in range(window - 1, T):
        block = x[t - window + 1 : t + 1]
        out[t] = np.nanmax(
            np.where(np.all(np.isnan(block), axis=0), np.nan, block), axis=0
        )
    return out


def ts_arg_min(arr: np.ndarray, window: int) -> np.ndarray:
    """Days-since-min: 0 means the min is the latest value."""
    x = np.asarray(arr, dtype=np.float64)
    T = x.shape[0]
    out = np.full_like(x, np.nan)
    if window < 1 or T < window:
        return out
    for t in range(window - 1, T):
        block = x[t - window + 1 : t + 1]
        # argmin from the end: window-1 - argmin
        with np.errstate(invalid="ignore"):
            idx = np.nanargmin(np.where(np.isnan(block), np.inf, block), axis=0)
        # When all-NaN per column, argmin returns 0; mask it
        all_nan = np.all(np.isnan(block), axis=0)
        out[t] = np.where(all_nan, np.nan, (window - 1) - idx)
    return out


def ts_arg_max(arr: np.ndarray, window: int) -> np.ndarray:
    x = np.asarray(arr, dtype=np.float64)
    T = x.shape[0]
    out = np.full_like(x, np.nan)
    if window < 1 or T < window:
        return out
    for t in range(window - 1, T):
        block = x[t - window + 1 : t + 1]
        with np.errstate(invalid="ignore"):
            idx = np.nanargmax(np.where(np.isnan(block), -np.inf, block), axis=0)
        all_nan = np.all(np.isnan(block), axis=0)
        out[t] = np.where(all_nan, np.nan, (window - 1) - idx)
    return out


def ts_covariance(a: np.ndarray, b: np.ndarray, window: int) -> np.ndarray:
    ax = np.asarray(a, dtype=np.float64)
    bx = np.asarray(b, dtype=np.float64)
    ma = ts_mean(ax, window)
    mb = ts_mean(bx, window)
    mab = ts_mean(ax * bx, window)
    return mab - ma * mb


def ts_quantile(arr: np.ndarray, window: int, q: float = 0.5) -> np.ndarray:
    """Rolling quantile q of the values within the trailing window."""
    x = np.asarray(arr, dtype=np.float64)
    T = x.shape[0]
    out = np.full_like(x, np.nan)
    if window < 1 or T < window:
        return out
    qf = float(q)
    for t in range(window - 1, T):
        block = x[t - window + 1 : t + 1]
        all_nan = np.all(np.isnan(block), axis=0)
        with np.errstate(invalid="ignore"):
            qv = np.nanquantile(block, qf, axis=0)
        out[t] = np.where(all_nan, np.nan, qv)
    return out


def ts_decay_linear(arr: np.ndarray, window: int) -> np.ndarray:
    """Weighted moving average with linearly increasing weights [1..window]."""
    x = np.asarray(arr, dtype=np.float64)
    T = x.shape[0]
    out = np.full_like(x, np.nan)
    if window < 1 or T < window:
        return out
    weights = np.arange(1, window + 1, dtype=np.float64)
    for t in range(window - 1, T):
        block = x[t - window + 1 : t + 1]
        valid = ~np.isnan(block)
        wsum = (weights[:, None] * valid).sum(axis=0)
        wval = (weights[:, None] * np.where(valid, block, 0.0)).sum(axis=0)
        with np.errstate(divide="ignore", invalid="ignore"):
            out[t] = np.where(wsum > 0, wval / wsum, np.nan)
    return out


def ts_decay_exp(arr: np.ndarray, window: int) -> np.ndarray:
    """Exponentially-weighted MA: weights[i] = (1 - 1/window)^(window-1-i)."""
    x = np.asarray(arr, dtype=np.float64)
    T = x.shape[0]
    out = np.full_like(x, np.nan)
    if window < 1 or T < window:
        return out
    decay = 1.0 - 1.0 / window
    weights = decay ** np.arange(window - 1, -1, -1, dtype=np.float64)
    for t in range(window - 1, T):
        block = x[t - window + 1 : t + 1]
        valid = ~np.isnan(block)
        wsum = (weights[:, None] * valid).sum(axis=0)
        wval = (weights[:, None] * np.where(valid, block, 0.0)).sum(axis=0)
        with np.errstate(divide="ignore", invalid="ignore"):
            out[t] = np.where(wsum > 0, wval / wsum, np.nan)
    return out


def ts_count_nans(arr: np.ndarray, window: int) -> np.ndarray:
    """Count of NaNs in the trailing window."""
    x = np.asarray(arr, dtype=np.float64)
    T = x.shape[0]
    out = np.full_like(x, np.nan)
    if window < 1 or T < window:
        return out
    is_n = np.isnan(x).astype(np.float64)
    cs = np.cumsum(is_n, axis=0)
    head = np.concatenate([np.zeros_like(cs[:1]), cs[:-window]], axis=0)[: T - window + 1]
    out[window - 1 :] = cs[window - 1 :] - head
    return out


def ts_regression(y: np.ndarray, x: np.ndarray, window: int) -> np.ndarray:
    """Rolling OLS slope of y on x over `window` periods (cov(x,y) / var(x))."""
    yx = np.asarray(y, dtype=np.float64)
    xx = np.asarray(x, dtype=np.float64)
    if window < 2:
        raise ValueError("ts_regression window must be >= 2")
    mx = ts_mean(xx, window)
    my = ts_mean(yx, window)
    mxy = ts_mean(xx * yx, window)
    mxx = ts_mean(xx * xx, window)
    cov = mxy - mx * my
    var = mxx - mx * mx
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(var > 0, cov / var, np.nan)


def ts_backfill(arr: np.ndarray, window: int) -> np.ndarray:
    """Replace NaN with the most recent non-NaN value within the trailing window."""
    x = np.asarray(arr, dtype=np.float64)
    out = x.copy()
    for j in range(x.shape[1] if x.ndim == 2 else 1):
        col = out if x.ndim == 1 else out[:, j]
        for t in range(len(col)):
            if np.isnan(col[t]):
                lo = max(0, t - window + 1)
                # walk back through window for the nearest non-NaN
                for k in range(t - 1, lo - 1, -1):
                    if not np.isnan(col[k]):
                        col[t] = col[k]
                        break
    return out


def trade_when(
    trigger: np.ndarray, alpha: np.ndarray, exit_when: np.ndarray
) -> np.ndarray:
    """Conditional alpha-holding signal.

    Semantics (WorldQuant): when `exit_when > 0` the position closes (NaN).
    When `trigger > 0` the alpha is emitted. Otherwise the previous alpha
    value is held. This converts an episodic alpha into a holding position.
    """
    tr = np.asarray(trigger, dtype=np.float64)
    al = np.asarray(alpha, dtype=np.float64)
    ex = np.asarray(exit_when, dtype=np.float64)
    if tr.shape != al.shape or al.shape != ex.shape:
        raise ValueError("trade_when: shapes must match")
    out = np.full_like(al, np.nan)
    T = al.shape[0]
    N = al.shape[1] if al.ndim == 2 else 1
    flat_al = al if al.ndim == 2 else al.reshape(-1, 1)
    flat_tr = tr if tr.ndim == 2 else tr.reshape(-1, 1)
    flat_ex = ex if ex.ndim == 2 else ex.reshape(-1, 1)
    flat_out = out if out.ndim == 2 else out.reshape(-1, 1)
    for j in range(N):
        prev = np.nan
        for t in range(T):
            if flat_ex[t, j] > 0:
                prev = np.nan
            elif flat_tr[t, j] > 0:
                prev = flat_al[t, j]
            # else: hold prev unchanged
            flat_out[t, j] = prev
    return out.reshape(al.shape)


def hump(arr: np.ndarray, threshold: float = 0.01) -> np.ndarray:
    """Smooth the signal by holding the previous value unless the relative
    change exceeds `threshold`. Reduces turnover at the cost of latency.

    Update rule: out[t] = out[t-1] unless |x[t] - out[t-1]| > threshold *
    (1 + |out[t-1]|), then out[t] = x[t]. The (1 + |.|) guards against the
    degenerate case where out[t-1] is near zero.
    """
    x = np.asarray(arr, dtype=np.float64)
    T = x.shape[0]
    N = x.shape[1] if x.ndim == 2 else 1
    flat_x = x if x.ndim == 2 else x.reshape(-1, 1)
    out = np.full_like(flat_x, np.nan)
    thr = float(threshold)
    for j in range(N):
        prev = np.nan
        for t in range(T):
            cur = flat_x[t, j]
            if np.isnan(prev):
                prev = cur
            elif not np.isnan(cur):
                delta = abs(cur - prev)
                if delta > thr * (1.0 + abs(prev)):
                    prev = cur
            out[t, j] = prev
    return out.reshape(x.shape)


def last_diff_value(arr: np.ndarray) -> np.ndarray:
    """Last value strictly different from the current — NaN if no prior diff exists."""
    x = np.asarray(arr, dtype=np.float64)
    T, N = x.shape if x.ndim == 2 else (x.shape[0], 1)
    flat = _as_2d(x)
    out = np.full_like(flat, np.nan)
    for j in range(flat.shape[1]):
        col = flat[:, j]
        last = np.nan
        for t in range(flat.shape[0]):
            cur = col[t]
            if not np.isnan(cur):
                # Walk backwards to find the most recent different value
                for k in range(t - 1, -1, -1):
                    pv = col[k]
                    if not np.isnan(pv) and pv != cur:
                        last = pv
                        break
            out[t, j] = last
    return out.reshape(x.shape)


# ── Cross-section (additions, axis=1) ───────────────────────────────────────


def zscore(arr: np.ndarray) -> np.ndarray:
    """Cross-sectional z-score per row."""
    x = np.asarray(arr, dtype=np.float64)
    x2 = _as_2d(x)
    out = np.full_like(x2, np.nan)
    for t in range(x2.shape[0]):
        row = x2[t]
        m = np.nanmean(row)
        s = np.nanstd(row)
        if s > 0:
            out[t] = (row - m) / s
    return out.reshape(x.shape)


def normalize(arr: np.ndarray) -> np.ndarray:
    """Cross-sectional demean (no division)."""
    x = np.asarray(arr, dtype=np.float64)
    x2 = _as_2d(x)
    out = np.full_like(x2, np.nan)
    for t in range(x2.shape[0]):
        row = x2[t]
        m = np.nanmean(row)
        out[t] = row - m
    return out.reshape(x.shape)


# ── Group ops (axis=1, partitioned by `group` label per row) ───────────────


def _group_apply(
    arr: np.ndarray,
    group: np.ndarray,
    fn: Callable[[np.ndarray], np.ndarray],
) -> np.ndarray:
    """Apply `fn` to each group of values within each row, then stitch back.

    `arr` and `group` must have shape (T, N). NaN cells are preserved as NaN
    in the output. Group labels can be any hashable type; np.unique handles
    strings, ints, and category codes equally.
    """
    x = np.asarray(arr, dtype=np.float64)
    out = np.full_like(x, np.nan)
    g = np.asarray(group)
    if g.shape != x.shape:
        raise ValueError(f"group shape {g.shape} != value shape {x.shape}")
    for t in range(x.shape[0]):
        row = x[t]
        labels = g[t]
        for gid in np.unique(labels):
            mask = labels == gid
            block = row[mask]
            valid = ~np.isnan(block)
            if not valid.any():
                continue
            transformed = fn(block)
            out[t, mask] = transformed
    return out


def group_rank(arr: np.ndarray, group: np.ndarray) -> np.ndarray:
    def _rank(vals: np.ndarray) -> np.ndarray:
        out = np.full_like(vals, np.nan, dtype=np.float64)
        mask = ~np.isnan(vals)
        n = int(mask.sum())
        if n == 0:
            return out
        order = vals[mask].argsort().argsort().astype(np.float64)
        out[mask] = (order + 1.0) / n
        return out
    return _group_apply(arr, group, _rank)


def group_zscore(arr: np.ndarray, group: np.ndarray) -> np.ndarray:
    def _zs(vals: np.ndarray) -> np.ndarray:
        m = np.nanmean(vals)
        s = np.nanstd(vals)
        if s == 0 or np.isnan(s):
            return np.full_like(vals, np.nan)
        return (vals - m) / s
    return _group_apply(arr, group, _zs)


def group_mean(arr: np.ndarray, group: np.ndarray) -> np.ndarray:
    def _mean(vals: np.ndarray) -> np.ndarray:
        m = np.nanmean(vals)
        return np.full_like(vals, m)
    return _group_apply(arr, group, _mean)


def group_scale(arr: np.ndarray, group: np.ndarray) -> np.ndarray:
    def _scale(vals: np.ndarray) -> np.ndarray:
        m = np.nanmean(vals)
        centered = vals - m
        norm = np.nansum(np.abs(centered))
        if norm == 0 or np.isnan(norm):
            return np.full_like(vals, np.nan)
        return centered / norm
    return _group_apply(arr, group, _scale)


def group_neutralize(arr: np.ndarray, group: np.ndarray) -> np.ndarray:
    """Subtract the within-group mean from each cell — the canonical group-neutral residual."""
    def _neut(vals: np.ndarray) -> np.ndarray:
        return vals - np.nanmean(vals)
    return _group_apply(arr, group, _neut)


def group_backfill(arr: np.ndarray, group: np.ndarray) -> np.ndarray:
    """Replace NaN cells with the within-group mean (a primitive imputation)."""
    def _backfill(vals: np.ndarray) -> np.ndarray:
        m = np.nanmean(vals)
        if np.isnan(m):
            return vals
        return np.where(np.isnan(vals), m, vals)
    return _group_apply(arr, group, _backfill)


def quantile(arr: np.ndarray, n_buckets: int = 5) -> np.ndarray:
    """Cross-sectional bucket index in {0, 1, ..., n_buckets-1}."""
    x = np.asarray(arr, dtype=np.float64)
    x2 = _as_2d(x)
    out = np.full_like(x2, np.nan)
    n_buckets = max(int(n_buckets), 1)
    for t in range(x2.shape[0]):
        row = x2[t]
        mask = ~np.isnan(row)
        n = int(mask.sum())
        if n == 0:
            continue
        ranks = np.full_like(row, np.nan)
        order = row[mask].argsort().argsort().astype(np.float64)
        # Bucketize 0..n_buckets-1
        ranks[mask] = np.minimum(
            (order * n_buckets / n).astype(np.int64), n_buckets - 1
        ).astype(np.float64)
        out[t] = ranks
    return out.reshape(x.shape)


# ── Operator registry (T1) ──────────────────────────────────────────────────


OPS: dict[str, Callable[..., np.ndarray]] = {
    # arithmetic — canonical BRAIN names + legacy short aliases
    "abs": abs_,
    "add": add,
    "subtract": sub,    "sub": sub,        # legacy alias
    "multiply": mul,    "mul": mul,
    "divide": div,      "div": div,
    "inverse": inverse,
    "log": log,
    "sqrt": sqrt,
    "power": pow_,      "pow": pow_,
    "sign": sign,
    "signed_power": signed_power,
    "max": max_,
    "min": min_,
    "reverse": reverse,
    "densify": densify,

    # logical
    "if_else": if_else,
    "and_": and_,
    "or_": or_,
    "not_": not_,
    "is_nan": is_nan,
    "equal": equal,
    "not_equal": not_equal,
    "less": less,
    "greater": greater,
    "less_equal": less_equal,
    "greater_equal": greater_equal,

    # time-series
    "ts_delay": ts_delay,
    "ts_delta": ts_delta,
    "ts_mean": ts_mean,
    "ts_std": ts_std,           # legacy alias
    "ts_std_dev": ts_std,
    "ts_sum": ts_sum,
    "ts_product": ts_product,
    "ts_min": ts_min,
    "ts_max": ts_max,
    "ts_rank": ts_rank,
    "ts_zscore": ts_zscore,
    "ts_arg_min": ts_arg_min,
    "ts_arg_max": ts_arg_max,
    "ts_corr": ts_corr,
    "ts_covariance": ts_covariance,
    "ts_quantile": ts_quantile,
    "ts_decay_linear": ts_decay_linear,
    "ts_decay_exp": ts_decay_exp,
    "ts_count_nans": ts_count_nans,
    "ts_regression": ts_regression,
    "ts_backfill": ts_backfill,
    "last_diff_value": last_diff_value,

    # cross-section
    "rank": rank,
    "zscore": zscore,
    "scale": scale,
    "normalize": normalize,
    "quantile": quantile,
    "winsorize": winsorize,

    # transformational (T3-promoted)
    "trade_when": trade_when,
    "hump": hump,

    # group (T2 — require sector/industry operand to be in the data dict)
    "group_rank": group_rank,
    "group_zscore": group_zscore,
    "group_mean": group_mean,
    "group_scale": group_scale,
    "group_neutralize": group_neutralize,
    "group_backfill": group_backfill,
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
    if isinstance(node, ast.UnaryOp):
        # `-1` / `+0.5` parse to UnaryOp(USub|UAdd, Constant). Negation works
        # on scalars and ndarrays alike via numpy's __neg__. validate_expression
        # already gated the operand to a numeric literal.
        operand = _eval_node(node.operand, data)
        if isinstance(node.op, ast.USub):
            return -operand
        if isinstance(node.op, ast.UAdd):
            return operand
        raise ValueError(f"unsupported unary op {type(node.op).__name__}")
    raise ValueError(f"unsupported AST node {type(node).__name__}")
