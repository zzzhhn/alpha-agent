"""Equal-weight quantile baskets and their close-to-close return alignment."""

from __future__ import annotations

import numpy as np


def quantile_weights(
    factor: np.ndarray,
    top_pct: float,
    bottom_pct: float,
    *,
    use_long: bool = True,
    use_short: bool = True,
) -> np.ndarray:
    """Build disjoint equal-weight legs from an ordered cross-section.

    With at least ten finite eligible names and a nonconstant score, each
    enabled side selects floor(N × fraction) names (at least one). A single
    stable ordering breaks partial ties in panel order; opposite tails never
    meet.
    """
    if not (0.0 < top_pct <= 0.5 and 0.0 < bottom_pct <= 0.5):
        raise ValueError("basket fractions must be in (0, 0.5]")
    weights = np.zeros(factor.shape, dtype=np.float64)
    eligible = np.isfinite(factor)
    for t, row in enumerate(factor):
        indices = np.flatnonzero(eligible[t])
        n = len(indices)
        if n < 10:
            continue
        order = indices[np.argsort(row[indices], kind="stable")]
        if row[order[0]] == row[order[-1]]:
            continue
        if use_long:
            n_long = max(1, int(n * top_pct))
            weights[t, order[-n_long:]] = 1.0 / n_long
        if use_short:
            n_short = max(1, int(n * bottom_pct))
            weights[t, order[:n_short]] = -1.0 / n_short
    return weights


def realized_basket_returns(
    weights: np.ndarray,
    fwd_returns: np.ndarray,
    *,
    require_exposure: bool = False,
) -> np.ndarray:
    """Realize weight[t] × forward_return[t] on date t+1, without reweighting.

    The kernel treats an empty basket as cash. Zoo requires at least one
    observed held position so warm-up/no-signal sessions aren't correlation
    observations. The absence of data never changes the decision weights.
    """
    daily = np.full(len(weights), np.nan)
    observed = np.isfinite(fwd_returns[:-1])
    if require_exposure:
        observed &= weights[:-1] != 0.0
    aligned_returns = np.where(observed, fwd_returns[:-1], 0.0)
    daily[1:] = np.where(observed.any(axis=1), (weights[:-1] * aligned_returns).sum(axis=1), np.nan)
    return daily
