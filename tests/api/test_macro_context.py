from datetime import datetime, UTC
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.asyncio


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgres://x/x")
    from api.index import app
    return TestClient(app)


def _pool_with_rows(rows):
    pool = MagicMock()
    pool.fetch = AsyncMock(return_value=rows)
    return pool


def test_macro_context_returns_events_with_ticker_in_extracted_array(client, monkeypatch):
    rows = [
        {"id": 1, "author": "trump", "title": "Apple should make iPhones in USA",
         "url": "https://truthsocial.com/x", "body": "...",
         "published_at": datetime(2026, 5, 16, tzinfo=UTC),
         "sentiment_score": -0.4,
         "tickers_extracted": ["AAPL"],
         "sectors_extracted": ["Information Technology"]},
    ]
    pool = _pool_with_rows(rows)
    monkeypatch.setattr(
        "alpha_agent.api.routes.macro_context.get_db_pool",
        AsyncMock(return_value=pool),
    )
    r = client.get("/api/macro_context?ticker=AAPL&limit=5")
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["title"].startswith("Apple should make")


def test_macro_context_empty_for_unknown_ticker(client, monkeypatch):
    pool = _pool_with_rows([])
    monkeypatch.setattr(
        "alpha_agent.api.routes.macro_context.get_db_pool",
        AsyncMock(return_value=pool),
    )
    r = client.get("/api/macro_context?ticker=ZZZZ&limit=5")
    assert r.status_code == 200
    assert r.json() == {"items": []}
