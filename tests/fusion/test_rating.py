# tests/fusion/test_rating.py
import math
from alpha_agent.fusion.rating import map_to_tier, compute_confidence


def test_tier_boundaries():
    assert map_to_tier(2.0) == "BUY"
    assert map_to_tier(1.5001) == "BUY"
    assert map_to_tier(1.4999) == "OW"
    assert map_to_tier(0.5001) == "OW"
    assert map_to_tier(0.4999) == "HOLD"
    assert map_to_tier(0.0) == "HOLD"
    assert map_to_tier(-0.5) == "HOLD"
    assert map_to_tier(-0.5001) == "UW"
    assert map_to_tier(-1.5) == "UW"
    assert map_to_tier(-1.5001) == "SELL"


def test_confidence_high_when_aligned():
    zs = [1.5, 1.4, 1.6, 1.5, 1.4]
    assert compute_confidence(zs) > 0.85


def test_confidence_low_on_disagreement():
    zs = [3.0, -3.0, 0.0, 2.0, -2.0]
    assert compute_confidence(zs) < 0.30


def test_confidence_empty_returns_zero():
    assert compute_confidence([]) == 0.0
