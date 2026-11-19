"""Small, pairwise-finite correlation helpers shared by research paths."""

from __future__ import annotations

import math

import numpy as np


def _average_ranks(values: np.ndarray) -> np.ndarray:
    """Assign all members of a tie group the mean of its zero-based ranks."""
    order = np.argsort(values, kind="stable")
    ordered = values[order]
    bounds = np.r_[0, np.flatnonzero(ordered[1:] != ordered[:-1]) + 1, len(order)]
    ranks = np.empty(len(order), dtype=np.float64)
    ranks[order] = np.repeat((bounds[:-1] + bounds[1:] - 1) / 2.0, np.diff(bounds))
    return ranks


def _centered_corr(x: np.ndarray, y: np.ndarray) -> float:
    if not np.any(x != x[0]) or not np.any(y != y[0]):
        return float("nan")
    x = x - x.mean()
    y = y - y.mean()
    # Scale each centered vector before taking its L2 norm, so small but
    # nonconstant return series aren't treated as undefined by a unit cutoff.
    x /= np.abs(x).max()
    y /= np.abs(y).max()
    c = np.dot(x, y) / math.sqrt(np.dot(x, x) * np.dot(y, y))
    return float(np.clip(c, -1.0, 1.0))


def pearson_corr(x: np.ndarray, y: np.ndarray) -> float:
    """Pearson r over common finite observations, or NaN if undefined."""
    mask = np.isfinite(x) & np.isfinite(y)
    if np.count_nonzero(mask) < 2:
        return float("nan")
    return _centered_corr(x[mask], y[mask])


def spearman_corr(x: np.ndarray, y: np.ndarray, *, min_count: int = 2) -> float:
    """Tie-correct Spearman rho over common finite observations."""
    mask = np.isfinite(x) & np.isfinite(y)
    if np.count_nonzero(mask) < min_count:
        return float("nan")
    return _centered_corr(_average_ranks(x[mask]), _average_ranks(y[mask]))


def nav_max_drawdown(returns: np.ndarray) -> float:
    """Largest peak-to-trough drop, including the opening NAV of 1.0."""
    clean = returns[np.isfinite(returns)]
    if not clean.size:
        return 0.0
    nav = np.cumprod(1.0 + clean)
    peak = np.maximum.accumulate(np.maximum(nav, 1.0))
    return float(np.min((nav - peak) / peak))
