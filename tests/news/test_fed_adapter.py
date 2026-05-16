from datetime import datetime, UTC
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.asyncio


async def test_fed_rss_adapter_parses_press_releases():
    from alpha_agent.news.fed_adapter import FedRSSAdapter

    adapter = FedRSSAdapter()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = (Path(__file__).parent / "fixtures" / "fed_press.xml").read_text()
    mock_resp.raise_for_status = MagicMock()
    adapter._client.get = AsyncMock(return_value=mock_resp)

    events = await adapter.fetch(since=datetime(2026, 5, 1, tzinfo=UTC))
    assert len(events) == 1
    e = events[0]
    assert e.source == "fed_rss"
    assert e.author == "fed"
    assert "FOMC statement" in e.title
    await adapter.aclose()
