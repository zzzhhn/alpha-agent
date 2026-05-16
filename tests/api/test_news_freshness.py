from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.asyncio


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgres://x/x")
    from api.index import app
    return TestClient(app)


def test_news_freshness_returns_one_row_per_known_source(client, monkeypatch):
    pool = MagicMock()
    # 6 expected sources, plus a fake one to confirm we only report known ones.
    pool.fetch = AsyncMock(return_value=[
        {"source": "finnhub",      "last_fetched_at": None, "items_24h": 1843},
        {"source": "fmp",          "last_fetched_at": None, "items_24h": 12},
        {"source": "rss_yahoo",    "last_fetched_at": None, "items_24h": 0},
        {"source": "truth_social", "last_fetched_at": None, "items_24h": 27},
        {"source": "fed_rss",      "last_fetched_at": None, "items_24h": 3},
        {"source": "ofac_rss",     "last_fetched_at": None, "items_24h": 1},
    ])
    pool.fetchval = AsyncMock(return_value=14)
    monkeypatch.setattr(
        "alpha_agent.api.routes.health.get_db_pool",
        AsyncMock(return_value=pool),
    )
    r = client.get("/api/_health/news_freshness")
    assert r.status_code == 200
    body = r.json()
    names = {s["name"] for s in body["sources"]}
    assert names == {"finnhub", "fmp", "rss_yahoo",
                     "truth_social", "fed_rss", "ofac_rss"}
    assert body["llm_backlog"] == 14
