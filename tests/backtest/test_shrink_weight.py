# tests/backtest/test_shrink_weight.py
"""Guarded-shrinkage weight math (council #6)."""
from alpha_agent.backtest.adaptive_weights import shrink_weight, SHRINK_MAX_DELTA


def test_no_evidence_stays_at_prior():
    # n_eff <= 0 -> no move (never hard-drop on sparse evidence).
    assert shrink_weight(0.30, 0.0, 0) == 0.30
    assert shrink_weight(0.30, 0.0, None) == 0.30


def test_move_is_capped_at_max_delta():
    # Aggressive evidence (0.0) vs prior 0.30 with huge sample: target would be
    # ~0.0, but the per-cycle move is capped at SHRINK_MAX_DELTA.
    w = shrink_weight(0.30, 0.0, 100_000, floor=0.02)
    assert abs(w - (0.30 - SHRINK_MAX_DELTA)) < 1e-9  # 0.25, not 0.0


def test_floor_prevents_hard_drop():
    # Even repeated cycles cannot drop below the floor.
    w = shrink_weight(0.04, 0.0, 100_000, floor=0.02, max_delta=0.05)
    assert w >= 0.02


def test_shrinkage_scales_with_sample():
    # More evidence -> larger pull toward evidence (still within max_delta).
    small = shrink_weight(0.30, 0.50, 5, max_delta=1.0)
    large = shrink_weight(0.30, 0.50, 300, max_delta=1.0)
    assert 0.30 < small < large <= 0.50


def test_cap_clamps_upside():
    w = shrink_weight(0.30, 0.90, 100_000, cap=0.32, max_delta=1.0)
    assert w == 0.32
