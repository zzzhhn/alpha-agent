import json
from datetime import datetime, UTC
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.asyncio


@pytest.fixture
def finnhub_response():
    p = Path(__file__).parent / "fixtures" / "finnhub_aapl_response.json"
    return json.loads(p.read_text())


async def test_finnhub_adapter_returns_normalized_news_items(finnhub_response, monkeypatch):
    from alpha_agent.news.finnhub_adapter import FinnhubAdapter

    adapter = FinnhubAdapter(api_key="fixture-key")
    # Mock the underlying httpx GET so the test never hits the network.
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = finnhub_response
    mock_resp.raise_for_status = MagicMock()
    adapter._client.get = AsyncMock(return_value=mock_resp)

    items = await adapter.fetch(ticker="AAPL", since=datetime(2026, 5, 1, tzinfo=UTC))

    assert len(items) == 2
    first = items[0]
    assert first.ticker == "AAPL"
    assert first.source == "finnhub"
    assert first.source_id == "7104210"
    assert first.headline == "Apple Beats Q2 Earnings Expectations, Stock Climbs"
    assert first.url == "https://www.cnbc.com/2026/05/15/apple-q2-earnings.html"
    assert first.published_at.year == 2024  # 1715783400 = 2024-05-15
    assert first.summary.startswith("Apple reported earnings")
    await adapter.aclose()


async def test_finnhub_adapter_dedup_hash_is_deterministic(finnhub_response, monkeypatch):
    from alpha_agent.news.finnhub_adapter import FinnhubAdapter

    a = FinnhubAdapter(api_key="k")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = finnhub_response
    mock_resp.raise_for_status = MagicMock()
    a._client.get = AsyncMock(return_value=mock_resp)
    items1 = await a.fetch(ticker="AAPL", since=datetime(2026, 5, 1, tzinfo=UTC))
    items2 = await a.fetch(ticker="AAPL", since=datetime(2026, 5, 1, tzinfo=UTC))
    assert items1[0].dedup() == items2[0].dedup()
    await a.aclose()


async def test_finnhub_adapter_empty_response_returns_empty_list(monkeypatch):
    from alpha_agent.news.finnhub_adapter import FinnhubAdapter

    adapter = FinnhubAdapter(api_key="k")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = []
    mock_resp.raise_for_status = MagicMock()
    adapter._client.get = AsyncMock(return_value=mock_resp)
    items = await adapter.fetch(ticker="ZZZZ", since=datetime(2026, 5, 1, tzinfo=UTC))
    assert items == []
    await adapter.aclose()


async def test_finnhub_adapter_429_raises_for_failover(monkeypatch):
    from alpha_agent.news.finnhub_adapter import FinnhubAdapter
    from httpx import HTTPStatusError, Request, Response

    adapter = FinnhubAdapter(api_key="k")
    req = Request("GET", "https://finnhub.io/api/v1/company-news")
    resp = Response(429, request=req)
    mock_resp = MagicMock()
    mock_resp.status_code = 429
    mock_resp.raise_for_status = MagicMock(
        side_effect=HTTPStatusError("429", request=req, response=resp)
    )
    adapter._client.get = AsyncMock(return_value=mock_resp)

    with pytest.raises(HTTPStatusError):
        await adapter.fetch(ticker="AAPL", since=datetime(2026, 5, 1, tzinfo=UTC))
    await adapter.aclose()
