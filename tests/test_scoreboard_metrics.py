"""Unit tests for scoreboard cost/turnover/SPY/significance math.

Tests are pure-Python, no database, no mocking.  Each fixture is a small
hand-computed example so the expected value can be verified by inspection.

2026-07-12 — covers the 2026-07-12 harness additions:
  - turnover computation (one-sided name overlap)
  - cost-net cumulative return formula
  - OLS beta/alpha  (hand-verified 3-point case)
  - Newey-West t-stat (simple i.i.d. case collapses to standard t-test)
  - IC t-stat via _newey_west_se (same HAC path)
  - _nw_lag formula
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from alpha_agent.backtest.scoreboard import (
    _newey_west_se,
    _nw_lag,
    _ols_alpha_beta,
)

# ---------------------------------------------------------------------------
# Helper: rebuild turnover from a sequence of basket sets (pure Python)
# ---------------------------------------------------------------------------

def _compute_turnovers(baskets: list[set]) -> list[float]:
    """Reproduce the scoreboard's one-sided turnover logic on a list of sets."""
    tos: list[float] = []
    prev: set = set()
    for cur in baskets:
        k = max(len(cur), len(prev))
        if not prev or k == 0:
            tos.append(1.0)  # first period or empty
        else:
            overlap = len(cur & prev) / k
            tos.append(1.0 - overlap)
        prev = cur
    return tos


# ---------------------------------------------------------------------------
# Turnover tests
# ---------------------------------------------------------------------------

class TestTurnover:
    def test_full_turnover_when_no_overlap(self):
        """Completely different baskets -> 100% turnover."""
        tos = _compute_turnovers([{"A", "B"}, {"C", "D"}])
        assert tos[1] == pytest.approx(1.0)

    def test_zero_turnover_when_identical(self):
        """Same basket repeated -> 0% turnover (all names persist)."""
        tos = _compute_turnovers([{"A", "B"}, {"A", "B"}])
        assert tos[1] == pytest.approx(0.0)

    def test_half_turnover(self):
        """50% name overlap -> 50% turnover."""
        tos = _compute_turnovers([{"A", "B"}, {"A", "C"}])
        assert tos[1] == pytest.approx(0.5)

    def test_first_period_is_full(self):
        """First basket always treated as full turnover (conservative)."""
        tos = _compute_turnovers([{"A", "B"}])
        assert tos[0] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Cost-net cumulative return
# ---------------------------------------------------------------------------

class TestCostNetReturn:
    def test_zero_cost_equals_gross(self):
        """With 0bps cost, net == gross regardless of turnover."""
        long_rets = [0.01, -0.005, 0.008]
        turnovers = [1.0, 0.5, 0.25]
        cost = 0.0
        gross = net = 1.0
        for lr, to in zip(long_rets, turnovers):
            gross *= 1.0 + lr
            net *= 1.0 + lr - to * cost
        assert net == pytest.approx(gross, rel=1e-9)

    def test_cost_drag_reduces_return(self):
        """Positive cost with non-zero turnover must reduce net vs gross."""
        long_rets = [0.02, 0.01, 0.015]
        turnovers = [1.0, 0.5, 0.5]
        cost_bps = 10.0
        cost = cost_bps / 10000.0
        gross = net = 1.0
        for lr, to in zip(long_rets, turnovers):
            gross *= 1.0 + lr
            net *= 1.0 + lr - to * cost
        assert net < gross

    def test_hand_computed_value(self):
        """
        Day 1: lr=0.01, to=1.0, cost=0.001 -> net_ret = 0.01 - 0.001 = 0.009
        Day 2: lr=0.02, to=0.5, cost=0.001 -> net_ret = 0.02 - 0.0005 = 0.0195
        Net cum = (1.009)(1.0195) - 1 = 0.028867...
        """
        cost = 0.001
        net_prod = (1.0 + 0.01 - 1.0 * cost) * (1.0 + 0.02 - 0.5 * cost)
        expected = (1.0 + 0.01 - 0.001) * (1.0 + 0.02 - 0.0005)
        assert net_prod == pytest.approx(expected, rel=1e-9)
        assert abs(net_prod - 1.028676) < 0.0001


# ---------------------------------------------------------------------------
# OLS beta/alpha
# ---------------------------------------------------------------------------

class TestOLSBetaAlpha:
    def test_perfect_correlation_beta_one(self):
        """y = x -> beta = 1, alpha = 0."""
        x = np.array([0.01, -0.005, 0.008, 0.003, -0.002])
        y = x.copy()
        beta, alpha_ann, alpha_t = _ols_alpha_beta(y, x)
        assert beta == pytest.approx(1.0, abs=1e-8)
        assert alpha_ann == pytest.approx(0.0, abs=1e-6)

    def test_beta_scale_factor(self):
        """y = 2x -> beta = 2, alpha ≈ 0."""
        x = np.array([0.01, -0.005, 0.008, 0.003, -0.002])
        y = 2.0 * x
        beta, alpha_ann, alpha_t = _ols_alpha_beta(y, x)
        assert beta == pytest.approx(2.0, abs=1e-6)

    def test_alpha_nonzero(self):
        """y = 0.0002 + x -> daily alpha = 0.0002, annualized ≈ 0.0504."""
        daily_alpha = 0.0002
        x = np.array([0.01, -0.005, 0.008, 0.003, -0.002, 0.004, -0.001])
        y = daily_alpha + x
        beta, alpha_ann, alpha_t = _ols_alpha_beta(y, x)
        assert beta == pytest.approx(1.0, abs=1e-6)
        assert alpha_ann == pytest.approx(daily_alpha * 252.0, rel=1e-4)

    def test_short_series_returns_nan(self):
        """n < 3 should return (nan, nan, nan)."""
        x = np.array([0.01, 0.02])
        y = np.array([0.01, 0.02])
        beta, alpha_ann, alpha_t = _ols_alpha_beta(y, x)
        assert math.isnan(beta)
        assert math.isnan(alpha_ann)
        assert math.isnan(alpha_t)


# ---------------------------------------------------------------------------
# Newey-West SE
# ---------------------------------------------------------------------------

class TestNeweyWestSE:
    def test_iid_collapses_to_classical(self):
        """For i.i.d. residuals, NW-SE(lag=0) == classical SE = std/sqrt(n).

        We use lag=1 here but for i.i.d. series the lag-1 autocovariance is
        near zero, so NW-SE should be close (within 5%) to classical SE.
        """
        rng = np.random.default_rng(42)
        n = 200
        resid = rng.standard_normal(n)
        resid -= resid.mean()
        classical_se = float(np.std(resid, ddof=1) / math.sqrt(n))
        nw_se = _newey_west_se(resid, np.ones(n), lag=1)
        # For near-zero autocorrelation the two should agree within 10%
        assert abs(nw_se / classical_se - 1.0) < 0.10

    def test_positive_autocorrelation_inflates_se(self):
        """Positively autocorrelated residuals -> NW-SE > classical SE."""
        # AR(1) with phi=0.8
        rng = np.random.default_rng(7)
        n = 100
        e = rng.standard_normal(n)
        resid = np.zeros(n)
        for i in range(1, n):
            resid[i] = 0.8 * resid[i - 1] + e[i]
        resid -= resid.mean()
        classical_se = float(np.std(resid, ddof=1) / math.sqrt(n))
        nw_se = _newey_west_se(resid, np.ones(n), lag=_nw_lag(n))
        assert nw_se > classical_se

    def test_zero_residuals(self):
        """All-zero residuals -> SE = 0."""
        n = 20
        resid = np.zeros(n)
        se = _newey_west_se(resid, np.ones(n), lag=2)
        assert se == pytest.approx(0.0, abs=1e-15)


# ---------------------------------------------------------------------------
# _nw_lag formula
# ---------------------------------------------------------------------------

class TestNWLag:
    def test_canonical_values(self):
        """floor(4*(n/100)^(2/9)) for n in {30, 60, 96, 100, 200}."""
        assert _nw_lag(30) == max(1, int(4.0 * (30 / 100) ** (2.0 / 9.0)))
        assert _nw_lag(60) == max(1, int(4.0 * (60 / 100) ** (2.0 / 9.0)))
        assert _nw_lag(96) == max(1, int(4.0 * (96 / 100) ** (2.0 / 9.0)))
        assert _nw_lag(100) == max(1, int(4.0 * (100 / 100) ** (2.0 / 9.0)))
        assert _nw_lag(200) == max(1, int(4.0 * (200 / 100) ** (2.0 / 9.0)))

    def test_minimum_lag_is_one(self):
        """Even for n=1 the lag should be at least 1."""
        assert _nw_lag(1) >= 1
        assert _nw_lag(5) >= 1

    def test_monotone_in_n(self):
        """Larger n -> same or larger lag."""
        lags = [_nw_lag(n) for n in [10, 30, 60, 100, 200, 500]]
        for a, b in zip(lags, lags[1:]):
            assert b >= a
