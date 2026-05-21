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


# ---------------------------------------------------------------------------
# Task 3: apply_change_cap and apply_floor_or_drop
# ---------------------------------------------------------------------------
from alpha_agent.backtest.adaptive_weights import (  # noqa: E402
    apply_change_cap,
    apply_floor_or_drop,
)


def test_change_cap_clamps_upward_move():
    # current=0.10, cap=0.15 -> max_step = 0.15 * max(0.10, 0.05) = 0.015.
    assert apply_change_cap(0.10, 0.50, cap_frac=0.15) == pytest.approx(0.115)


def test_change_cap_clamps_downward_move():
    assert apply_change_cap(0.10, 0.0, cap_frac=0.15) == pytest.approx(0.085)


def test_change_cap_lets_dropped_signal_re_grow_slowly():
    # current=0 -> reference is CAP_MIN_REF=0.05 -> max_step = 0.15*0.05 = 0.0075.
    assert apply_change_cap(0.0, 0.30, cap_frac=0.15) == pytest.approx(0.0075)


def test_floor_shrinks_on_single_bad_window_not_zero():
    # icir <= 0 is a bad window; with cb below the max, weight shrinks to the
    # floor (not a hard zero) and the bad counter increments.
    w, cb, dropped = apply_floor_or_drop(
        raw_target=0.0, icir=-0.3, consecutive_bad=0, floor=0.02, max_bad=3
    )
    assert w == pytest.approx(0.02) and cb == 1 and dropped is False


def test_hard_drop_after_max_consecutive_bad():
    w, cb, dropped = apply_floor_or_drop(
        raw_target=0.0, icir=-0.1, consecutive_bad=2, floor=0.02, max_bad=3
    )
    assert w == 0.0 and cb == 3 and dropped is True


def test_good_window_resets_counter_and_keeps_target():
    w, cb, dropped = apply_floor_or_drop(
        raw_target=0.18, icir=1.2, consecutive_bad=2, floor=0.02, max_bad=3
    )
    assert w == pytest.approx(0.18) and cb == 0 and dropped is False
