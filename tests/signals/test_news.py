# tests/signals/test_news.py
from datetime import datetime, UTC
from unittest.mock import patch
from alpha_agent.signals.news import fetch_signal


def test_positive_news_yields_positive_z():
    items = [{"title": "Apple beats earnings", "sentiment": 0.8},
             {"title": "Strong iPhone sales", "sentiment": 0.6}]
    with patch("alpha_agent.signals.news._search_recent", return_value=items):
        out = fetch_signal("AAPL", datetime(2024, 12, 15, tzinfo=UTC))
    assert out["z"] > 0


def test_no_news_low_confidence():
    with patch("alpha_agent.signals.news._search_recent", return_value=[]):
        out = fetch_signal("XYZ", datetime(2024, 12, 15, tzinfo=UTC))
    assert out["confidence"] < 0.4
