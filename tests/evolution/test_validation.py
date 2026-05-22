import numpy as np
import pytest

from alpha_agent.evolution.validation import deflated_sharpe_lite, purged_fold_indices


def test_purged_folds_embargo_excludes_overlap():
    folds = purged_fold_indices(n=100, n_folds=5, embargo=5)
    assert len(folds) == 5
    for train_idx, test_idx in folds:
        lo, hi = min(test_idx), max(test_idx)
        assert all(not (lo - 5 <= t <= hi + 5) for t in train_idx)


def test_deflated_sharpe_lite_penalizes_trial_count():
    s = [0.1, 0.2, 0.9]
    d_few = deflated_sharpe_lite(best_sharpe=0.9, sharpes=s, n_trials=3)
    d_many = deflated_sharpe_lite(best_sharpe=0.9, sharpes=s, n_trials=30)
    assert d_many < d_few
    assert deflated_sharpe_lite(best_sharpe=0.2, sharpes=[0.18, 0.2, 0.22], n_trials=20) <= 0.2
