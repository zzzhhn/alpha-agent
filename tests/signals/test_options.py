# tests/signals/test_options.py
from datetime import datetime, UTC
from unittest.mock import patch
from alpha_agent.signals.options import fetch_signal


def test_high_put_call_negative_z():
    chain = {"calls_volume": 1000, "puts_volume": 3000, "iv_percentile": 60}
    with patch("alpha_agent.signals.options._fetch_chain", return_value=chain):
        out = fetch_signal("AAPL", datetime(2024, 12, 15, tzinfo=UTC))
    assert out["z"] < 0


def test_low_put_call_positive_z():
    chain = {"calls_volume": 5000, "puts_volume": 1000, "iv_percentile": 30}
    with patch("alpha_agent.signals.options._fetch_chain", return_value=chain):
        out = fetch_signal("AAPL", datetime(2024, 12, 15, tzinfo=UTC))
    assert out["z"] > 0
