"""Tests for the serenity supply-chain bottleneck signal (integration seam #2).

Covers the scoring port (parity with the serenity rubric), the score -> z
mapping, and the SignalScore contract (z=None when unscored, real z when primed).
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from alpha_agent.signals import supply_chain
from alpha_agent.signals.supply_chain_scorecard import (
    WEIGHTS,
    score_card,
    score_to_z,
)

_AS_OF = datetime(2026, 6, 16, tzinfo=UTC)


def test_weights_sum_to_100():
    assert sum(WEIGHTS.values()) == 100


def test_score_card_all_max_no_penalty_is_100():
    data = {"factors": {k: 5 for k in WEIGHTS}}
    r = score_card(data)
    assert r["final_score"] == 100.0
    assert r["verdict"] == "Top research priority"


def test_score_card_all_zero_is_0():
    r = score_card({"factors": {k: 0 for k in WEIGHTS}})
    assert r["final_score"] == 0.0
    assert r["verdict"] == "Early lead or low priority"


def test_score_card_penalty_subtracts_twice_the_rating():
    # All factors max (100) minus one penalty rated 5 => 100 - 5*2 = 90.
    data = {"factors": {k: 5 for k in WEIGHTS}, "penalties": {"governance": 5}}
    r = score_card(data)
    assert r["final_score"] == 90.0
    assert r["penalty_points"] == 10.0


def test_score_card_rejects_out_of_range_rating():
    with pytest.raises(ValueError):
        score_card({"factors": {"demand_inflection": 9}})


def test_score_to_z_endpoints_and_center():
    assert score_to_z(50.0) == pytest.approx(0.0)
    assert score_to_z(100.0) == pytest.approx(3.0)
    assert score_to_z(0.0) == pytest.approx(-3.0)
    # clip holds beyond the band
    assert score_to_z(200.0) == 3.0


def test_signal_unscored_emits_none_z(monkeypatch):
    monkeypatch.setattr(supply_chain, "_SCORECARD_CACHE", {})
    sc = supply_chain.fetch_signal("AAPL", _AS_OF)
    assert sc["z"] is None
    assert sc["confidence"] == 0.0
    assert sc["source"] == "serenity-scorecard"
    assert sc["error"]


def test_signal_primed_emits_mapped_z_and_evidence_confidence():
    supply_chain.prime_cache(
        {"NVDA": {"final_score": 83.0, "verdict": "High research priority",
                  "evidence_quality": 5.0}}
    )
    try:
        sc = supply_chain.fetch_signal("nvda", _AS_OF)
        assert sc["z"] == pytest.approx(score_to_z(83.0))
        assert sc["z"] > 0  # strong bottleneck -> positive tilt
        assert sc["confidence"] == pytest.approx(0.9)  # max evidence_quality
        assert sc["raw"]["final_score"] == 83.0
        assert sc["error"] is None
    finally:
        supply_chain.prime_cache({})
