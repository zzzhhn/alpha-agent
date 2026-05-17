"""Tests for the rewritten news signal (Phase 6a Task 5).

Methodology:
- LLM-as-Judge 12-bucket: rows tagged with (impact_bucket, direction_bucket)
  feed Tetlock-style impact_weight * direction_sign aggregation.
- Loughran-McDonald fallback: rows with no LLM tags get scored via the
  financial dictionary at lower confidence.
- Confidence tiers: 0.7 all-LLM, 0.5 mixed, 0.3 pure LM or empty.

Tests monkeypatch _query_recent_news to avoid live DB.
"""
from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from alpha_agent.signals.news import compute_news_signal


_BUCKET_FIXTURE = [
    {"id": 1, "ticker": "AAPL",
     "headline": "Apple beats earnings, strong revenue growth",
     "impact_bucket": "high", "direction_bucket": "bullish",
     "sentiment_score": None,
     "published_at": datetime(2026, 5, 15, 14, 30, tzinfo=UTC)},
    {"id": 2, "ticker": "AAPL",
     "headline": "Apple disclosed antitrust lawsuit",
     "impact_bucket": "medium", "direction_bucket": "bearish",
     "sentiment_score": None,
     "published_at": datetime(2026, 5, 15, 15, 0, tzinfo=UTC)},
    {"id": 3, "ticker": "AAPL",
     "headline": "Apple announces routine quarterly report filing",
     "impact_bucket": "none", "direction_bucket": "neutral",
     "sentiment_score": None,
     "published_at": datetime(2026, 5, 15, 15, 30, tzinfo=UTC)},
]


@pytest.mark.asyncio
async def test_tetlock_score_from_buckets():
    """Mixed buckets, expect Tetlock score in (-1, +1), confidence 0.7 (all LLM)."""
    with patch("alpha_agent.signals.news._query_recent_news",
               return_value=_BUCKET_FIXTURE):
        sig = await compute_news_signal("AAPL")
    assert -1.0 <= sig["raw"]["mean_sent"] <= 1.0
    # high+bullish = 1.0 * +1; medium+bearish = 0.7 * -1; none+neutral = 0
    # weighted by row count 3, expect (1.0 - 0.7 + 0) / 3 = 0.1
    assert abs(sig["raw"]["mean_sent"] - 0.1) < 0.05
    assert sig["confidence"] >= 0.7
    assert sig["raw"]["n"] == 3
    assert len(sig["raw"]["headlines"]) == 3


@pytest.mark.asyncio
async def test_lm_fallback_when_no_bucket():
    """Rows with no LLM bucket fall through to LM dictionary at confidence 0.3."""
    no_llm = [
        {"id": 1, "ticker": "AAPL",
         "headline": "Apple posts outstanding profitable record results",
         "impact_bucket": None, "direction_bucket": None,
         "sentiment_score": None,
         "published_at": datetime(2026, 5, 15, 14, 30, tzinfo=UTC)},
    ]
    with patch("alpha_agent.signals.news._query_recent_news", return_value=no_llm):
        sig = await compute_news_signal("AAPL")
    assert sig["confidence"] == 0.3
    # LM dict tags as bullish, mean_sent should be positive
    assert sig["raw"]["mean_sent"] > 0


@pytest.mark.asyncio
async def test_empty_news_returns_low_confidence_zero():
    with patch("alpha_agent.signals.news._query_recent_news", return_value=[]):
        sig = await compute_news_signal("AAPL")
    assert sig["raw"]["n"] == 0
    assert sig["raw"]["mean_sent"] == 0.0
    assert sig["confidence"] == 0.3
