# tests/fusion/test_attribution.py
from alpha_agent.fusion.attribution import top_drivers, top_drags


def test_top_drivers_picks_top_3_positive():
    breakdown = [
        {"signal": "factor", "contribution": +0.54},
        {"signal": "tech", "contribution": +0.30},
        {"signal": "analyst", "contribution": +0.20},
        {"signal": "macro", "contribution": -0.18},
        {"signal": "news", "contribution": -0.12},
    ]
    drivers = top_drivers(breakdown, n=3)
    assert drivers == ["factor", "tech", "analyst"]


def test_top_drags_picks_most_negative():
    breakdown = [
        {"signal": "factor", "contribution": +0.54},
        {"signal": "macro", "contribution": -0.18},
        {"signal": "news", "contribution": -0.12},
        {"signal": "premkt", "contribution": -0.06},
    ]
    drags = top_drags(breakdown, n=2)
    assert drags == ["macro", "news"]


def test_zero_contribution_signals_excluded():
    breakdown = [
        {"signal": "a", "contribution": +0.5},
        {"signal": "b", "contribution": 0.0},
    ]
    assert top_drivers(breakdown, n=3) == ["a"]
    assert top_drags(breakdown, n=3) == []
