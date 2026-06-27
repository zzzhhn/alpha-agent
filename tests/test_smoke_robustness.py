"""Smoke-test perturbation-robustness gauge (AlphaEval dimension 3).

A genuine alpha should survive small input noise: if a 3% multiplicative jitter
on the input operands reshuffles the cross-sectional ranking, the factor is
curve-fit to the exact numbers and will not hold out-of-sample. AlphaEval calls
this "Robustness to Market Perturbations" and injects Gaussian (normal vol) +
Student-t (fat-tail shock) noise, then measures rank consistency before/after.

smoke_test estimates this on the synthetic panel: re-evaluate the factor on
noise-perturbed inputs and average the Spearman rank correlation between the
clean and perturbed rankings. A robust LEVEL factor (rank of a fundamental)
stays ~0.99; a noise-AMPLIFYING factor (a difference / a spread of two
near-equal quantities, where small input noise dominates the output) collapses
toward 0. Surfaced so the API can warn before a fragile factor reaches a full
backtest. This is the input-perturbation axis the project previously lacked (it
already had multiple-testing robustness via deflated Sharpe and regime
robustness, but no input-noise check).

Calibration note: this is NOT the same as "noisy predictor". rank(returns)
scores ~1.0 because a 3% multiplicative jitter barely reorders the
cross-sectional ranking of returns — it is robust to input noise even though it
is a weak predictor. What the gauge actually catches is noise AMPLIFICATION:
differencing (ts_delta, sub of a lagged copy) and knife-edge spreads of
near-equal quantities (sub(rank(high), rank(low))), which score 0.0-0.25.
"""
from __future__ import annotations

import math

from alpha_agent.scan.smoke import smoke_test

_EP = "divide(net_income_adjusted,multiply(close,shares_outstanding))"
# Robust: rank of a per-ticker-stable fundamental — 3% jitter barely reorders it
# (measured ~0.99).
_ROBUST = "rank(equity)"
# Fragile: a difference of a signal and its lagged self — differencing amplifies
# the noise, so the perturbed ranking decorrelates from the clean one (~0.25).
_FRAGILE = "ts_delta(rank(close),1)"
# Knife-edge: spread of two near-equal quantities — output is dominated by the
# noise on the tiny difference (~0.05). The clearest fragile signature.
_KNIFE_EDGE = "sub(rank(close),rank(vwap))"


def test_robust_factor_survives_noise():
    r = smoke_test(_ROBUST, lookback=60)
    assert math.isfinite(r.robustness)
    assert r.robustness > 0.7, (
        f"a rank-of-stable-fundamental should be noise-robust, got "
        f"{r.robustness:.3f}"
    )


def test_fragile_difference_factor_collapses_under_noise():
    r = smoke_test(_FRAGILE, lookback=60)
    assert r.robustness < 0.5, (
        f"a differencing factor amplifies noise, expected low robustness, got "
        f"{r.robustness:.3f}"
    )


def test_knife_edge_spread_is_flagged_fragile():
    r = smoke_test(_KNIFE_EDGE, lookback=60)
    assert r.robustness < 0.5, (
        f"a near-equal spread is noise-dominated, got {r.robustness:.3f}"
    )


def test_robustness_separates_robust_from_fragile():
    """The gauge's whole point: the robust factor must hold its ranking under
    noise far better than the fragile one, so a single threshold flags it."""
    robust = smoke_test(_ROBUST, lookback=60).robustness
    fragile = smoke_test(_FRAGILE, lookback=60).robustness
    assert robust > fragile + 0.3, (
        f"separation too small: robust={robust:.3f} fragile={fragile:.3f}"
    )


def test_value_factor_is_reasonably_robust():
    """The canonical E/P value factor (close moves, fundamentals stable) should
    land on the robust side — the gate must not false-positive it."""
    r = smoke_test(f"rank({_EP})", lookback=60)
    assert r.robustness > 0.6, f"E/P value factor flagged fragile: {r.robustness:.3f}"
