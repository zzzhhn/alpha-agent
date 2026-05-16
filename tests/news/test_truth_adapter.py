import json
from datetime import datetime, UTC
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.asyncio


async def test_truth_social_adapter_normalizes_truth_archive():
    from alpha_agent.news.truth_adapter import TruthSocialAdapter
    payload = json.loads(
        (Path(__file__).parent / "fixtures" / "truth_archive.json").read_text()
    )
    adapter = TruthSocialAdapter()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = payload
    mock_resp.raise_for_status = MagicMock()
    adapter._client.get = AsyncMock(return_value=mock_resp)

    events = await adapter.fetch(since=datetime(2026, 5, 1, tzinfo=UTC))
    assert len(events) == 2
    e = events[0]
    assert e.source == "truth_social"
    assert e.author == "trump"
    assert e.body.startswith("Apple should make iPhones")
    assert e.published_at.year == 2026
    assert e.url and "truthsocial.com" in e.url
    await adapter.aclose()
