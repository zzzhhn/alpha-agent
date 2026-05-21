# tests/backtest/test_confidence_calibration_math.py
import pytest

from alpha_agent.backtest.confidence_calibration import (
    _pava,
    apply_calibration,
    isotonic_fit,
)


def test_pava_is_non_decreasing():
    out = _pava([0.3, 0.1, 0.2, 0.9, 0.4])
    assert all(out[i] <= out[i + 1] + 1e-12 for i in range(len(out) - 1))


def test_isotonic_none_below_min_pairs():
    # Fewer than MIN_PAIRS (50) -> None (identity fallback).
    assert isotonic_fit([(0.5, 1)] * 49) is None


def test_isotonic_suppresses_overconfident_region():
    # 60 pairs, 5 confidence levels, realized hit-rate = confidence * 0.5
    # (systematically overconfident). The fitted map at high confidence must
    # sit well below the diagonal.
    pairs = []
    for conf in (0.1, 0.3, 0.5, 0.7, 0.9):
        n_hit = round(12 * conf * 0.5)
        pairs += [(conf, 1)] * n_hit + [(conf, 0)] * (12 - n_hit)
    cal = isotonic_fit(pairs)
    assert cal is not None
    mapped_high = float(__import__("numpy").interp(0.9, cal["x"], cal["y"]))
    assert mapped_high < 0.6  # 0.9 stated -> well below, near ~0.45


def test_apply_calibration_is_suppress_only():
    cal = {"x": [0.0, 1.0], "y": [0.0, 0.4]}  # maps 0.9 -> 0.36
    assert apply_calibration(0.9, cal) == pytest.approx(0.36)
    # A map that would RAISE confidence is clamped to raw (never inflates).
    cal_up = {"x": [0.0, 1.0], "y": [0.0, 1.0]}  # maps 0.5 -> 0.5
    assert apply_calibration(0.5, cal_up) == pytest.approx(0.5)
    cal_inflate = {"x": [0.0, 1.0], "y": [0.5, 1.0]}  # maps 0.2 -> 0.6 (inflation)
    assert apply_calibration(0.2, cal_inflate) == pytest.approx(0.2)  # clamped


def test_apply_calibration_identity_when_no_map():
    assert apply_calibration(0.77, None) == pytest.approx(0.77)
    assert apply_calibration(0.77, {"x": [], "y": []}) == pytest.approx(0.77)
