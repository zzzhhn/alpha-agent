# tests/signals/test_news.py
"""Tests for news signal backed by news_items Postgres table.

These tests monkeypatch alpha_agent.signals.news._query_recent_news (the
async DB-querying coroutine) so the signal logic can be exercised without
a live database connection.
"""
from datetime import UTC, datetime, timedelta

from alpha_agent.signals.news import fetch_signal


def _row(headline, sentiment_score, sentiment_label="pos", offset_min=0):
    """Build a news_items-shaped row dict for tests."""
    return {
        "headline": headline,
        "source": "WSJ",
        "url": f"https://example.com/{headline.replace(' ', '_')}",
        "published_at": datetime(2026, 5, 16, 9, 0, tzinfo=UTC)
        + timedelta(minutes=offset_min),
        "sentiment_score": sentiment_score,
        "sentiment_label": sentiment_label,
    }


def _patch_query(monkeypatch, rows):
    """Replace _query_recent_news with an async stub returning rows."""
    async def _stub(_ticker):
        return rows
    monkeypatch.setattr(
        "alpha_agent.signals.news._query_recent_news", _stub,
    )


def test_positive_news_yields_positive_z(monkeypatch):
    rows = [
        _row(f"Apple beats earnings {i}", sentiment_score=0.6,
             sentiment_label="pos", offset_min=i)
        for i in range(5)
    ]
    _patch_query(monkeypatch, rows)

    out = fetch_signal("AAPL", datetime(2026, 5, 16, tzinfo=UTC))

    assert out["z"] > 0
    assert out["raw"]["n"] == 5
    assert out["raw"]["mean_sent"] > 0
    assert out["confidence"] == 0.7
    assert out["source"] == "news_items"
    assert out["error"] is None
    assert out["raw"]["headlines"][0]["sentiment"] == "pos"
    assert out["raw"]["headlines"][0]["publisher"] == "WSJ"


def test_negative_news_yields_negative_z(monkeypatch):
    rows = [
        _row(f"Stock plunges {i}", sentiment_score=-0.6,
             sentiment_label="neg", offset_min=i)
        for i in range(5)
    ]
    _patch_query(monkeypatch, rows)

    out = fetch_signal("AAPL", datetime(2026, 5, 16, tzinfo=UTC))

    assert out["z"] < 0
    assert out["raw"]["n"] == 5
    assert out["raw"]["mean_sent"] < 0
    assert out["confidence"] == 0.7
    assert out["raw"]["headlines"][0]["sentiment"] == "neg"


def test_no_news_low_confidence(monkeypatch):
    _patch_query(monkeypatch, [])

    out = fetch_signal("XYZ", datetime(2026, 5, 16, tzinfo=UTC))

    assert out["z"] == 0.0
    assert out["confidence"] == 0.3
    assert out["error"] == "no news in last 24h"
    assert out["raw"]["n"] == 0
    assert out["raw"]["headlines"] == []


def test_caps_headlines_at_ten(monkeypatch):
    rows = [
        _row(f"Headline {i}", sentiment_score=0.1,
             sentiment_label="pos", offset_min=i)
        for i in range(20)
    ]
    _patch_query(monkeypatch, rows)

    out = fetch_signal("AAPL", datetime(2026, 5, 16, tzinfo=UTC))

    assert out["raw"]["n"] == 20
    assert len(out["raw"]["headlines"]) == 10
