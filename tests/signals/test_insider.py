# tests/signals/test_insider.py
from datetime import datetime, UTC
from unittest.mock import patch
from alpha_agent.signals.insider import fetch_signal


def test_net_buying_yields_positive_z():
    fills = [{"code": "P", "shares": 1000, "value": 200_000},
             {"code": "P", "shares": 500, "value": 100_000}]
    with patch("alpha_agent.signals.insider._fetch_form4_30d", return_value=fills):
        out = fetch_signal("AAPL", datetime(2024, 12, 15, tzinfo=UTC))
    assert out["z"] > 0
    assert out["raw"]["net_value"] > 0


def test_no_filings_zero_z_low_confidence():
    with patch("alpha_agent.signals.insider._fetch_form4_30d", return_value=[]):
        out = fetch_signal("XYZ", datetime(2024, 12, 15, tzinfo=UTC))
    assert out["z"] == 0.0
    assert out["confidence"] < 0.5
