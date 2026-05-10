# tests/signals/test_calendar.py
from datetime import datetime, UTC
from unittest.mock import patch
from alpha_agent.signals import calendar as cal


def test_calendar_returns_zero_z_carries_events():
    events = [{"name": "FOMC", "date": "2024-12-18", "days_to": 3}]
    with patch("alpha_agent.signals.calendar._fetch_events", return_value=events):
        out = cal.fetch_signal("AAPL", datetime(2024, 12, 15, tzinfo=UTC))
    assert out["z"] == 0.0
    assert out["raw"][0]["name"] == "FOMC"
