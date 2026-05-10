# tests/signals/test_macro.py
from datetime import datetime, UTC
from unittest.mock import patch
from alpha_agent.signals.macro import fetch_signal


def test_macro_inversion_negative_for_growth():
    snapshot = {"DGS10": 4.0, "DGS2": 4.5, "DXY": 105, "VIX": 18}
    with patch("alpha_agent.signals.macro._fetch_snapshot", return_value=snapshot):
        out = fetch_signal("AAPL", datetime(2024, 12, 15, tzinfo=UTC))
    assert out["z"] < 0  # inverted curve = risk-off
    assert "DGS10" in out["raw"]


def test_macro_steep_curve_positive():
    snapshot = {"DGS10": 4.5, "DGS2": 4.0, "DXY": 100, "VIX": 14}
    with patch("alpha_agent.signals.macro._fetch_snapshot", return_value=snapshot):
        out = fetch_signal("AAPL", datetime(2024, 12, 15, tzinfo=UTC))
    assert out["z"] > 0
