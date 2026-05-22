import pytest

from alpha_agent.evolution.candidates import enumerate_candidates


def test_enumerates_bounded_neighbors_of_current_config():
    current = {
        "rating.tier_thresholds": {"buy": 1.5, "ow": 0.5, "hold": -0.5, "uw": -1.5},
        "rating.no_trade_band": 0.15,
        "factor.mode": "short",
        "signal.ic_accept_threshold": 0.02,
    }
    cands = enumerate_candidates(current)
    # Each candidate is a single-knob delta from current (local search).
    assert all(c.key in current for c in cands)
    # The band knob proposes +/- a step (e.g. 0.10 and 0.20 around 0.15).
    band_vals = sorted(c.new_value for c in cands if c.key == "rating.no_trade_band")
    assert band_vals == [pytest.approx(0.10), pytest.approx(0.20)]
    # factor.mode proposes the flip.
    modes = [c.new_value for c in cands if c.key == "factor.mode"]
    assert modes == ["long"]
    # Bounded: total candidate count is small (hard cap, e.g. <= 8).
    assert 1 <= len(cands) <= 8
