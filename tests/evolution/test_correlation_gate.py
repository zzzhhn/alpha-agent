"""Phase B1: the SELF_CORRELATION gate — reject a candidate whose daily
long-short returns are too correlated with an already-saved factor (a WQ-style
redundancy check). The pure correlation core is unit-tested here; the panel-
backed IO path is covered end-to-end by the factor-lab API tests."""
import numpy as np

from alpha_agent.evolution.correlation_gate import (
    SelfCorrelationGate,
    max_corr_against,
)


def test_max_corr_against_picks_the_strongest_abs():
    cand = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    existing = {
        "same": np.array([2.0, 4.0, 6.0, 8.0, 10.0]),   # +1 correlated
        "opposite": np.array([5.0, 4.0, 3.0, 2.0, 1.0]),  # -1 correlated
        "flat_noise": np.array([1.0, -1.0, 1.0, -1.0, 1.0]),
    }
    corr, name = max_corr_against(cand, existing)
    # |corr| picks up the perfectly (anti-)correlated series
    assert corr > 0.99
    assert name in ("same", "opposite")


def test_max_corr_against_empty_is_zero():
    assert max_corr_against(np.array([1.0, 2.0, 3.0]), {}) == (0.0, None)


def test_gate_with_no_existing_factors_is_a_noop():
    """No saved factors → the gate never loads the panel and always passes
    (0.0 correlation), so a fresh install proposes exactly as before."""
    gate = SelfCorrelationGate(existing=[])
    assert gate.check("rank(ts_mean(returns, 12))") == (0.0, None)
