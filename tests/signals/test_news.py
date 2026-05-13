# tests/signals/test_news.py
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from alpha_agent.signals.news import fetch_signal


def _ticker_mock(news_payload):
    m = MagicMock()
    m.news = news_payload
    return m


def test_positive_news_yields_positive_z():
    payload = [
        {"title": "Apple beats Q3 earnings, raises guidance",
         "publisher": "WSJ", "providerPublishTime": 1700000000, "link": "x"},
        {"title": "Strong iPhone sales surge",
         "publisher": "Bloomberg", "providerPublishTime": 1700000100, "link": "y"},
    ]
    with patch("alpha_agent.signals.news.get_ticker",
               return_value=_ticker_mock(payload)):
        out = fetch_signal("AAPL", datetime(2026, 5, 13, tzinfo=UTC))
    assert out["z"] > 0
    assert out["raw"]["n"] == 2
    assert out["raw"]["headlines"][0]["sentiment"] == "pos"
    assert out["raw"]["headlines"][0]["publisher"] == "WSJ"


def test_negative_news_yields_negative_z():
    payload = [
        {"title": "Stock plunges on weak iPhone sales",
         "publisher": "Reuters", "providerPublishTime": 1700000000, "link": "x"},
        {"title": "Apple misses analyst estimates",
         "publisher": "FT", "providerPublishTime": 1700000100, "link": "y"},
    ]
    with patch("alpha_agent.signals.news.get_ticker",
               return_value=_ticker_mock(payload)):
        out = fetch_signal("AAPL", datetime(2026, 5, 13, tzinfo=UTC))
    assert out["z"] < 0


def test_no_news_low_confidence():
    with patch("alpha_agent.signals.news.get_ticker",
               return_value=_ticker_mock([])):
        out = fetch_signal("XYZ", datetime(2026, 5, 13, tzinfo=UTC))
    assert out["confidence"] < 0.4
    assert out["raw"]["n"] == 0
    assert out["raw"]["headlines"] == []


def test_caps_headlines_at_five():
    payload = [
        {"title": f"Headline {i}", "publisher": "Reuters",
         "providerPublishTime": 1700000000 + i * 60, "link": f"x{i}"}
        for i in range(10)
    ]
    with patch("alpha_agent.signals.news.get_ticker",
               return_value=_ticker_mock(payload)):
        out = fetch_signal("AAPL", datetime(2026, 5, 13, tzinfo=UTC))
    assert len(out["raw"]["headlines"]) == 5
