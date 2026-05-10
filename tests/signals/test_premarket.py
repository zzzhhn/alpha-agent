# tests/signals/test_premarket.py
from datetime import datetime, UTC
from unittest.mock import patch
from alpha_agent.signals.premarket import fetch_signal


def test_3sigma_gap_up_positive():
    info = {"preMarketPrice": 105, "regularMarketPreviousClose": 100, "atr14": 1.0}
    with patch("alpha_agent.signals.premarket._fetch_premarket", return_value=info):
        out = fetch_signal("AAPL", datetime(2024, 12, 15, 8, tzinfo=UTC))
    assert out["z"] > 1.5  # gap of 5 / atr 1 = 5σ → clipped


def test_no_premarket_data_low_conf():
    with patch("alpha_agent.signals.premarket._fetch_premarket", return_value={}):
        out = fetch_signal("AAPL", datetime(2024, 12, 15, 8, tzinfo=UTC))
    assert out["confidence"] < 0.4
