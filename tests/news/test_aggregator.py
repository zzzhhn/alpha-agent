from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.asyncio


def _stub_adapter(name, channel, priority, fetch_return):
    a = MagicMock()
    a.name = name
    a.channel = channel
    a.priority = priority
    a.fetch = AsyncMock(return_value=fetch_return)
    a.is_available = AsyncMock(return_value=True)
    a.aclose = AsyncMock(return_value=None)
    return a


async def test_per_ticker_aggregator_uses_primary_when_it_returns_items():
    from alpha_agent.news.aggregator import PerTickerAggregator
    from alpha_agent.news.types import NewsItem

    item = NewsItem(
        ticker="AAPL", source="finnhub", source_id="1",
        headline="Apple beats", url="https://x.com/a",
        published_at=datetime(2026, 5, 15, tzinfo=UTC),
    )
    finnhub = _stub_adapter("finnhub", "per_ticker", 1, [item])
    fmp     = _stub_adapter("fmp",     "per_ticker", 2, [])
    rss     = _stub_adapter("rss_yahoo", "per_ticker", 3, [])
    agg = PerTickerAggregator([finnhub, fmp, rss])
    result = await agg.fetch(ticker="AAPL", since=datetime(2026, 5, 1, tzinfo=UTC))
    assert len(result) == 1
    # FMP and RSS NOT called because primary returned items.
    fmp.fetch.assert_not_called()
    rss.fetch.assert_not_called()


async def test_per_ticker_aggregator_failovers_to_fmp_on_primary_empty():
    from alpha_agent.news.aggregator import PerTickerAggregator
    from alpha_agent.news.types import NewsItem

    finnhub = _stub_adapter("finnhub", "per_ticker", 1, [])
    fmp_item = NewsItem(
        ticker="AAPL", source="fmp", source_id=None,
        headline="From FMP", url="https://x.com/b",
        published_at=datetime(2026, 5, 15, tzinfo=UTC),
    )
    fmp = _stub_adapter("fmp", "per_ticker", 2, [fmp_item])
    rss = _stub_adapter("rss_yahoo", "per_ticker", 3, [])
    agg = PerTickerAggregator([finnhub, fmp, rss])
    result = await agg.fetch(ticker="AAPL", since=datetime(2026, 5, 1, tzinfo=UTC))
    assert len(result) == 1
    assert result[0].source == "fmp"
    rss.fetch.assert_not_called()


async def test_per_ticker_aggregator_circuit_breaker_opens_after_5_failures():
    from alpha_agent.news.aggregator import PerTickerAggregator
    from alpha_agent.news.types import NewsItem

    finnhub = _stub_adapter("finnhub", "per_ticker", 1, [])
    finnhub.fetch = AsyncMock(side_effect=Exception("upstream down"))
    fmp_item = NewsItem(
        ticker="AAPL", source="fmp", source_id=None,
        headline="From FMP", url="https://x.com/b",
        published_at=datetime(2026, 5, 15, tzinfo=UTC),
    )
    fmp = _stub_adapter("fmp", "per_ticker", 2, [fmp_item])
    rss = _stub_adapter("rss_yahoo", "per_ticker", 3, [])
    agg = PerTickerAggregator([finnhub, fmp, rss])
    # First 5 calls record_failure; on the 6th the breaker is open.
    for _ in range(5):
        await agg.fetch(ticker="AAPL", since=datetime(2026, 5, 1, tzinfo=UTC))
    finnhub.fetch.reset_mock()
    await agg.fetch(ticker="AAPL", since=datetime(2026, 5, 1, tzinfo=UTC))
    finnhub.fetch.assert_not_called()  # breaker open, skipped


async def test_macro_aggregator_calls_all_macro_sources_in_parallel():
    from alpha_agent.news.aggregator import MacroAggregator
    from alpha_agent.news.types import MacroEvent

    e1 = MacroEvent(source="truth_social", source_id="1", author="trump",
                    title="t", url="u", body="b",
                    published_at=datetime(2026, 5, 16, tzinfo=UTC))
    e2 = MacroEvent(source="fed_rss", source_id="2", author="fed",
                    title="fomc", url="u2", body="b",
                    published_at=datetime(2026, 5, 16, tzinfo=UTC))
    truth = _stub_adapter("truth_social", "macro", 1, [e1])
    fed   = _stub_adapter("fed_rss",      "macro", 1, [e2])
    ofac  = _stub_adapter("ofac_rss",     "macro", 1, [])
    agg = MacroAggregator([truth, fed, ofac])
    events = await agg.fetch_all(since=datetime(2026, 5, 1, tzinfo=UTC))
    assert len(events) == 2
    # Failover NOT used in macro; every adapter is called regardless.
    truth.fetch.assert_awaited_once()
    fed.fetch.assert_awaited_once()
    ofac.fetch.assert_awaited_once()
