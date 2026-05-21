# tests/backtest/test_adaptive_weights_math.py
from datetime import date, timedelta

import pytest

from alpha_agent.backtest.adaptive_weights import compute_ewma_icir


def _series(ics, start=None):
    """Build [(date, ic), ...] one trading day apart, oldest first."""
    start = start or (date.today() - timedelta(days=len(ics)))
    return [(start + timedelta(days=i), ic) for i, ic in enumerate(ics)]


def test_constant_series_has_zero_std_returns_none():
    # std == 0 -> ICIR undefined -> None (no risk-adjusted signal).
    assert compute_ewma_icir(_series([0.1, 0.1, 0.1]), half_life_days=30) is None


def test_single_point_returns_none():
    assert compute_ewma_icir(_series([0.1]), half_life_days=30) is None


def test_equal_weight_limit_matches_plain_mean_over_std():
    # half_life huge -> lambda ~ 1 -> equal weights -> plain (population) mean/std.
    # ic = [0.0, 0.1, 0.2]: mean=0.1, pop var=0.006667, std=0.081650, icir=1.2247.
    icir = compute_ewma_icir(_series([0.0, 0.1, 0.2]), half_life_days=1e9)
    assert icir == pytest.approx(1.2247, rel=1e-3)


def test_recent_points_dominate_with_short_half_life():
    # Recent ICs negative, old positive. A short half-life weights the recent
    # (negative) end, so ICIR must be negative.
    icir = compute_ewma_icir(_series([0.3, 0.2, -0.2, -0.3]), half_life_days=2)
    assert icir is not None and icir < 0
