"""Phase B1: the SELF_CORRELATION gate — reject a candidate whose daily
long-short returns are too correlated with an already-saved factor (a WQ-style
redundancy check). The pure correlation core is unit-tested here; the panel-
backed IO path is covered end-to-end by the factor-lab API tests."""
import numpy as np

from alpha_agent.evolution.correlation_gate import (
    SelfCorrelationGate,
    incremental_contribution,
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


# --- G1: incremental (basket-level) orthogonality gate ---------------------
def test_incremental_contribution_novel_when_basket_empty():
    c = np.random.default_rng(0).standard_normal(120)
    assert incremental_contribution(c, {}) == (1.0, None)


def test_incremental_contribution_low_when_basket_spans_candidate():
    rng = np.random.default_rng(1)
    a, b = rng.standard_normal(300), rng.standard_normal(300)
    cand = 0.6 * a + 0.4 * b + 1e-6 * rng.standard_normal(300)
    m, who = incremental_contribution(cand, {"a": a, "b": b})
    assert m < 0.1
    assert who in {"a", "b"}


def test_incremental_contribution_high_when_orthogonal():
    rng = np.random.default_rng(2)
    a, b = rng.standard_normal(300), rng.standard_normal(300)
    cand = rng.standard_normal(300)  # independent of the basket
    m, _ = incremental_contribution(cand, {"a": a, "b": b})
    assert m > 0.7


def test_incremental_contribution_catches_collective_low_rank():
    # THE money case: candidate is BELOW 0.7 pairwise with every basket series,
    # so the pairwise gate would pass it — but it's fully spanned by the trio,
    # so the basket gate must reject it (marginal ~0).
    rng = np.random.default_rng(3)
    a, b, c = (rng.standard_normal(500) for _ in range(3))
    cand = (a + b + c) / np.sqrt(3)
    pw, _ = max_corr_against(cand, {"a": a, "b": b, "c": c})
    m, _ = incremental_contribution(cand, {"a": a, "b": b, "c": c})
    assert pw < 0.7   # pairwise gate would NOT flag this
    assert m < 0.15   # basket gate DOES flag it
