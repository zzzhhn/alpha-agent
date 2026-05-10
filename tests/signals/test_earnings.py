# tests/signals/test_earnings.py
from datetime import datetime, timedelta, UTC
from unittest.mock import patch
from alpha_agent.signals.earnings import fetch_signal


def test_recent_beat_yields_positive_z():
    info = {
        "earningsDate": [datetime.now(UTC) - timedelta(days=5)],
        "epsActual": 1.20, "epsEstimate": 1.00,
    }
    with patch("alpha_agent.signals.earnings._fetch_info", return_value=info):
        out = fetch_signal("AAPL", datetime.now(UTC))
    assert out["z"] > 0
    assert out["raw"]["surprise_pct"] > 0


def test_no_data_low_confidence():
    with patch("alpha_agent.signals.earnings._fetch_info", return_value={}):
        out = fetch_signal("XYZ", datetime.now(UTC))
    assert out["confidence"] < 0.4
