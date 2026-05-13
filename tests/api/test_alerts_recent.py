# tests/api/test_alerts_recent.py
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from api.index import app
    return TestClient(app)


def _fake_row(ticker, type_, payload, dedup_bucket, created_at_iso):
    """Mirrors asyncpg.Record row shape via dict subscript access."""
    return {
        "id": 42,
        "ticker": ticker,
        "type": type_,
        "payload": payload,
        "dedup_bucket": dedup_bucket,
        "created_at": __import__("datetime").datetime.fromisoformat(created_at_iso),
    }


def test_alerts_recent_returns_latest_n(client, monkeypatch):
    rows = [
        _fake_row("AAPL", "rating_change", '{"from":"HOLD","to":"OW"}',
                  1715000000, "2026-05-14T10:00:00+00:00"),
        _fake_row("MSFT", "score_spike", '{"delta":0.45}',
                  1715000100, "2026-05-14T09:55:00+00:00"),
    ]
    pool = MagicMock()
    pool.fetch = AsyncMock(return_value=rows)
    monkeypatch.setattr(
        "alpha_agent.api.routes.alerts.get_db_pool",
        AsyncMock(return_value=pool),
    )
    r = client.get("/api/alerts/recent?limit=20")
    assert r.status_code == 200
    body = r.json()
    assert len(body["alerts"]) == 2
    assert body["alerts"][0]["ticker"] == "AAPL"
    assert body["alerts"][0]["type"] == "rating_change"
    assert body["alerts"][0]["payload"] == {"from": "HOLD", "to": "OW"}
    assert body["alerts"][0]["created_at"].startswith("2026-05-14T10:00:00")
    # SQL was called with limit but no ticker filter
    call_args = pool.fetch.call_args
    assert call_args.args[-1] == 20
    assert "WHERE ticker" not in call_args.args[0]


def test_alerts_recent_ticker_filter(client, monkeypatch):
    rows = [_fake_row("AAPL", "rating_change", '{}', 1, "2026-05-14T10:00:00+00:00")]
    pool = MagicMock()
    pool.fetch = AsyncMock(return_value=rows)
    monkeypatch.setattr(
        "alpha_agent.api.routes.alerts.get_db_pool",
        AsyncMock(return_value=pool),
    )
    r = client.get("/api/alerts/recent?ticker=AAPL&limit=5")
    assert r.status_code == 200
    assert len(r.json()["alerts"]) == 1
    call_args = pool.fetch.call_args
    assert "WHERE ticker" in call_args.args[0]
    assert call_args.args[1] == "AAPL"


def test_alerts_recent_empty_returns_empty_list(client, monkeypatch):
    pool = MagicMock()
    pool.fetch = AsyncMock(return_value=[])
    monkeypatch.setattr(
        "alpha_agent.api.routes.alerts.get_db_pool",
        AsyncMock(return_value=pool),
    )
    r = client.get("/api/alerts/recent")
    assert r.status_code == 200
    assert r.json()["alerts"] == []


def test_alerts_recent_invalid_limit_rejected(client):
    r = client.get("/api/alerts/recent?limit=999")  # cap is 100
    assert r.status_code == 422
