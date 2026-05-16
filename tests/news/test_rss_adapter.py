from datetime import datetime, UTC
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.asyncio


@pytest.fixture
def rss_xml():
    p = Path(__file__).parent / "fixtures" / "rss_yahoo_aapl.xml"
    return p.read_text()


async def test_rss_adapter_parses_yahoo_feed(rss_xml):
    from alpha_agent.news.rss_adapter import RSSAdapter

    adapter = RSSAdapter()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = rss_xml
    mock_resp.raise_for_status = MagicMock()
    adapter._client.get = AsyncMock(return_value=mock_resp)

    items = await adapter.fetch(ticker="AAPL", since=datetime(2026, 5, 1, tzinfo=UTC))

    # Both items in the fixture are after since=May 1.
    assert len(items) == 2
    titles = [i.headline for i in items]
    assert "Apple Eyes AI Hardware Partnership With OpenAI" in titles
    assert all(i.source == "rss_yahoo" for i in items)
    assert all(i.ticker == "AAPL" for i in items)
    await adapter.aclose()


async def test_rss_adapter_filters_by_since(rss_xml):
    from alpha_agent.news.rss_adapter import RSSAdapter

    adapter = RSSAdapter()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = rss_xml
    mock_resp.raise_for_status = MagicMock()
    adapter._client.get = AsyncMock(return_value=mock_resp)

    # since later than both items
    items = await adapter.fetch(ticker="AAPL", since=datetime(2026, 5, 16, tzinfo=UTC))
    assert items == []
    await adapter.aclose()
