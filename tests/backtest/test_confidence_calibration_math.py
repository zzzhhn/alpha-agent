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


from alpha_agent.backtest.confidence_calibration import reliability_and_brier  # noqa: E402


def test_reliability_buckets_hit_rate_and_brier():
    # Two clear buckets: conf 0.1 (hit-rate 0.0) and conf 0.9 (hit-rate 1.0).
    pairs = [(0.1, 0)] * 10 + [(0.9, 1)] * 10
    buckets = reliability_and_brier(pairs, n_buckets=10)
    by = {(b["lo"], b["hi"]): b for b in buckets if b["n"] > 0}
    low = next(b for k, b in by.items() if k[0] <= 0.1 < k[1])
    high = next(b for k, b in by.items() if k[0] <= 0.9 < k[1])
    assert low["hit_rate"] == pytest.approx(0.0)
    assert high["hit_rate"] == pytest.approx(1.0)
    # Brier in the 0.1 bucket: mean((0.1-0)^2) = 0.01; in 0.9 bucket: (0.9-1)^2 = 0.01.
    assert low["brier"] == pytest.approx(0.01)
    assert high["brier"] == pytest.approx(0.01)
    assert low["n"] == 10 and high["n"] == 10
