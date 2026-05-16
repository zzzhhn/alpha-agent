from datetime import datetime, UTC
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.asyncio


async def test_ofac_rss_adapter_parses_recent_actions():
    from alpha_agent.news.ofac_adapter import OFACRSSAdapter

    adapter = OFACRSSAdapter()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = (Path(__file__).parent / "fixtures" / "ofac_actions.xml").read_text()
    mock_resp.raise_for_status = MagicMock()
    adapter._client.get = AsyncMock(return_value=mock_resp)

    events = await adapter.fetch(since=datetime(2026, 5, 1, tzinfo=UTC))
    assert len(events) == 1
    e = events[0]
    assert e.source == "ofac_rss"
    assert e.author == "ofac"
    assert "Sanctions" in e.title
    await adapter.aclose()
