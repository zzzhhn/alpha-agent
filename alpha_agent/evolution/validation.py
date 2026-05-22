"""Purged walk-forward + Deflated-Sharpe-lite (numpy only, no scipy/sklearn).

SLICE A: purged_fold_indices + deflated_sharpe_lite  -- pure math, no IO.
SLICE B: CandidateResult + evaluate_candidate        -- real DB + kernel.
"""
from __future__ import annotations

import numpy as np


def purged_fold_indices(n: int, n_folds: int, embargo: int) -> list[tuple[list[int], list[int]]]:
    """Contiguous-block walk-forward folds with a purge+embargo gap: each test
    block excludes `embargo` train days on both sides so a label that overlaps
    the test window cannot leak into training."""
    bounds = np.linspace(0, n, n_folds + 1).astype(int)
    folds = []
    for i in range(n_folds):
        lo, hi = bounds[i], bounds[i + 1] - 1
        test_idx = list(range(lo, hi + 1))
        train_idx = [t for t in range(n) if t < lo - embargo or t > hi + embargo]
        folds.append((train_idx, test_idx))
    return folds


def deflated_sharpe_lite(best_sharpe: float, sharpes: list[float], n_trials: int) -> float:
    """Discount the best observed Sharpe by the cross-trial spread times
    log(n_trials) (more trials -> more selection bias -> larger haircut). Lite
    proxy for the Deflated Sharpe Ratio."""
    arr = np.asarray(sharpes, dtype=float)
    spread = float(arr.std()) if len(arr) > 1 else 0.0
    haircut = spread * float(np.log1p(n_trials))
    return float(best_sharpe - haircut)
