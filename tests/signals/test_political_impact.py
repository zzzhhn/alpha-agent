"""Tests for political_impact signal (Phase 6a Task 6).

Methodology:
- Sources rows from macro_events WHERE ticker appears in tickers_extracted.
- Same Tetlock-style aggregation as news signal but over a 7-day window
  (macro events have longer market half-life than daily ticker news).
- Confidence tiers: 0.7 all-LLM, 0.5 mixed, 0.3 pure LM or empty.

Tests monkeypatch _query_recent_macro to avoid live DB.
"""
from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from alpha_agent.signals.political_impact import compute_political_impact_signal


_MACRO_FIXTURE = [
    {"id": 1, "title": "Trump praises Tesla manufacturing", "body": "...",
     "author": "trump", "impact_bucket": "high", "direction_bucket": "bullish",
     "sentiment_score": 0.7, "url": "https://truthsocial.com/...",
     "published_at": datetime(2026, 5, 15, 14, 30, tzinfo=UTC)},
    {"id": 2, "title": "Trump signals tariff on Chinese imports", "body": "...",
     "author": "trump", "impact_bucket": "medium", "direction_bucket": "bearish",
     "sentiment_score": -0.5, "url": "https://truthsocial.com/...",
     "published_at": datetime(2026, 5, 16, 10, 00, tzinfo=UTC)},
]


@pytest.mark.asyncio
async def test_tesla_political_lane_only_after_a3_split():
    """A3 (2026-05-19): political_impact now filters to political category
    only. Row 1 ('Trump praises Tesla manufacturing') is political; row 2
    ('Trump signals tariff on Chinese imports') matches a geopolitical
    keyword (tariff) and reroutes to geopolitical_impact. So political
    sees n=1 here, not 2."""
    with patch("alpha_agent.signals.political_impact._query_recent_macro",
               return_value=_MACRO_FIXTURE):
        sig = await compute_political_impact_signal("TSLA")
    assert sig["raw"]["n"] == 1
    assert sig["raw"]["category"] == "political"
    assert sig["confidence"] >= 0.5  # LLM bucket present on the kept row
    # Single row: impact=high (1.0) * direction=bullish (+1) = 1.0
    assert abs(sig["raw"]["mean_sent"] - 1.0) < 0.05


@pytest.mark.asyncio
async def test_tesla_geopolitical_lane_after_a3_split():
    """A3 sibling test: the tariff row routes to geopolitical_impact."""
    from alpha_agent.signals.geopolitical_impact import compute_geopolitical_impact_signal
    with patch("alpha_agent.signals.geopolitical_impact._query_recent_macro",
               return_value=_MACRO_FIXTURE):
        sig = await compute_geopolitical_impact_signal("TSLA")
    assert sig["raw"]["n"] == 1
    assert sig["raw"]["category"] == "geopolitical"
    # Single row: impact=medium (0.7) * direction=bearish (-1) = -0.7
    assert abs(sig["raw"]["mean_sent"] - (-0.7)) < 0.05


@pytest.mark.asyncio
async def test_ticker_with_no_macro_events_low_confidence():
    with patch("alpha_agent.signals.political_impact._query_recent_macro",
               return_value=[]):
        sig = await compute_political_impact_signal("AAPL")
    assert sig["raw"]["n"] == 0
    assert sig["confidence"] == 0.3
    assert sig["raw"]["mean_sent"] == 0.0
