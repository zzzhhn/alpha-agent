# tests/fusion/test_rating_configurable.py
import pytest

from alpha_agent import config_store
from alpha_agent.fusion.rating import map_to_tier


def test_map_to_tier_uses_default_thresholds():
    config_store._CACHE.clear()
    assert map_to_tier(2.0) == "BUY"     # > 1.5 default
    assert map_to_tier(0.0) == "HOLD"
    assert map_to_tier(0.8) == "OW"      # > 0.5 default
    assert map_to_tier(-2.0) == "SELL"


def test_map_to_tier_honors_config_override():
    config_store._CACHE.clear()
    config_store._CACHE["rating.tier_thresholds"] = {"buy": 1.0, "ow": 0.5, "hold": -0.5, "uw": -1.5}
    try:
        assert map_to_tier(1.2) == "BUY"   # 1.2 > 1.0 configured (was OW under 1.5)
    finally:
        config_store._CACHE.clear()


def test_map_to_tier_nan_still_hold():
    config_store._CACHE.clear()
    assert map_to_tier(float("nan")) == "HOLD"
