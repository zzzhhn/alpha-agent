# tests/signals/test_analyst.py
from datetime import datetime, UTC
from unittest.mock import patch
from alpha_agent.signals.analyst import fetch_signal


def test_strong_buy_yields_positive_z():
    info = {"recommendationKey": "strong_buy", "targetMeanPrice": 250.0,
            "currentPrice": 200.0}
    with patch("alpha_agent.signals.analyst._fetch_info", return_value=info):
        out = fetch_signal("AAPL", datetime(2024, 12, 15, tzinfo=UTC))
    assert out["z"] > 0
    assert out["confidence"] > 0.7
    assert out["raw"]["recommendation"] == "strong_buy"


def test_missing_recommendation_low_confidence():
    with patch("alpha_agent.signals.analyst._fetch_info", return_value={}):
        out = fetch_signal("XYZ", datetime(2024, 12, 15, tzinfo=UTC))
    assert out["confidence"] < 0.3
