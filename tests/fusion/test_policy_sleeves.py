import pytest

from alpha_agent.fusion.policy import get_policy
from alpha_agent.api.routes.picks import _strategic_projection


def test_strategic_policy_is_independent_and_frozen():
    tactical = get_policy("tactical")
    strategic = get_policy("strategic")

    assert tactical.policy_id != strategic.policy_id
    assert tactical.horizon == "5d"
    assert strategic.horizon == "60d"
    assert sum(strategic.weights.values()) == pytest.approx(1.0)
    assert strategic.weights["technicals"] == 0.0
    assert strategic.weights["news"] == 0.0
    assert strategic.weights["factor"] > tactical.weights["factor"]
    assert set(strategic.core_signals) == {"factor", "analyst", "earnings", "macro"}


def test_unknown_sleeve_fails_closed():
    with pytest.raises(ValueError, match="unknown policy sleeve"):
        get_policy("same-score-with-a-new-label")


def test_strategic_projection_uses_long_factor_and_own_weights():
    def entry(signal, z, raw=None):
        return {
            "signal": signal,
            "z": z,
            "confidence": 1.0,
            "weight": 0.5,
            "weight_effective": 0.5,
            "contribution": z * 0.5,
            "raw": raw or {},
            "source": "test",
            "timestamp": "2026-08-03T00:00:00+00:00",
            "error": None,
        }

    result = _strategic_projection({"breakdown": [
        entry("factor", 2.0, {"z_long": -2.0}),
        entry("technicals", 3.0),
        entry("analyst", 0.0),
        entry("earnings", 0.0),
        entry("macro", 0.0),
    ]})
    factor = next(row for row in result["breakdown"] if row["signal"] == "factor")
    technicals = next(row for row in result["breakdown"] if row["signal"] == "technicals")
    assert factor["z"] == -2.0
    assert technicals["weight_effective"] == 0.0
    assert result["composite_score"] < 0


def test_missing_long_factor_does_not_fall_back_to_tactical_z():
    result = _strategic_projection({"breakdown": [{
        "signal": "factor", "z": 5.0, "confidence": 1.0,
        "weight": 1.0, "weight_effective": 1.0, "contribution": 5.0,
        "raw": {}, "source": "test", "timestamp": "2026-08-03T00:00:00+00:00",
        "error": None,
    }]})
    assert result["composite_score"] == 0.0
    assert result["coverage"] < 1.0
