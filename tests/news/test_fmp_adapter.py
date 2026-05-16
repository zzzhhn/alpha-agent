import json
from datetime import datetime, UTC
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.asyncio


@pytest.fixture
def fmp_response():
    p = Path(__file__).parent / "fixtures" / "fmp_aapl_response.json"
    return json.loads(p.read_text())


async def test_fmp_adapter_returns_normalized_news_items(fmp_response):
    from alpha_agent.news.fmp_adapter import FMPAdapter

    adapter = FMPAdapter(api_key="k")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = fmp_response
    mock_resp.raise_for_status = MagicMock()
    adapter._client.get = AsyncMock(return_value=mock_resp)

    items = await adapter.fetch(ticker="AAPL", since=datetime(2026, 5, 1, tzinfo=UTC))
    assert len(items) == 1
    it = items[0]
    assert it.ticker == "AAPL"
    assert it.source == "fmp"
    assert it.headline == "Apple Said to Plan India Manufacturing Expansion"
    assert it.url == "https://site.financialmodelingprep.com/market-news/aapl-india"
    assert it.published_at.year == 2026
    await adapter.aclose()


async def test_fmp_adapter_priority_is_two(fmp_response):
    """Failover-only behavior is enforced by the aggregator using
    adapter.priority. Locking the constant here prevents accidental
    promotion to primary."""
    from alpha_agent.news.fmp_adapter import FMPAdapter
    assert FMPAdapter(api_key="k").priority == 2
