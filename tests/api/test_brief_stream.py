# tests/api/test_brief_stream.py
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from api.index import app
    return TestClient(app)


def _make_row(ticker="AAPL"):
    return {
        "ticker": ticker,
        "rating": "OW",
        "composite": 1.42,
        "breakdown": json.dumps({
            "breakdown": [
                {"signal": "factor", "z": 1.5,
                 "raw": {"z": 1.5,
                         "fundamentals": {"pe_trailing": 28.5, "market_cap": 3.2e12,
                                          "eps_ttm": 6.42, "beta": 1.21,
                                          "pe_forward": None, "dividend_yield": None,
                                          "profit_margin": None, "debt_to_equity": None}}},
                {"signal": "news", "z": 0.6,
                 "raw": {"n": 2, "mean_sent": 0.5,
                         "headlines": [
                             {"title": "Apple beats earnings", "publisher": "WSJ",
                              "published_at": "2026-05-14T09:00:00Z", "link": "x",
                              "sentiment": "pos"},
                         ]}},
                {"signal": "earnings", "z": 0.4,
                 "raw": {"surprise_pct": 12.0, "days_to_earnings": 5,
                         "next_date": "2026-07-31", "days_until": 78,
                         "eps_estimate": 1.45, "revenue_estimate": 120e9}},
            ],
        }),
        "fetched_at": __import__("datetime").datetime.fromisoformat("2026-05-14T10:00:00+00:00"),
    }


async def _fake_stream():
    """Mimics LiteLLM streaming chunk shape minimally."""
    for token in ["Apple", " is", " trading", " at", " 28.5x", "."]:
        yield token


def test_brief_stream_emits_sse_deltas(client, monkeypatch):
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value=_make_row())
    monkeypatch.setattr(
        "alpha_agent.api.routes.brief.get_db_pool",
        AsyncMock(return_value=pool),
    )
    # Patch the streamer so the test doesn't need a real LLM key
    async def fake_stream(*args, **kwargs):
        async for tok in _fake_stream():
            yield {"type": "summary", "delta": tok}
        yield {"type": "done"}
    monkeypatch.setattr(
        "alpha_agent.api.routes.brief.stream_brief", fake_stream,
    )
    body = {"provider": "openai", "api_key": "sk-test"}
    with client.stream("POST", "/api/brief/AAPL/stream", json=body) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        chunks = b"".join(r.iter_bytes()).decode()
    lines = [ln for ln in chunks.splitlines() if ln.startswith("data: ")]
    parsed = [json.loads(ln[len("data: "):]) for ln in lines]
    assert parsed[0] == {"type": "summary", "delta": "Apple"}
    assert parsed[-1] == {"type": "done"}
    assert any(p.get("delta") == " 28.5x" for p in parsed)


def test_brief_stream_unknown_ticker_404(client, monkeypatch):
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "alpha_agent.api.routes.brief.get_db_pool",
        AsyncMock(return_value=pool),
    )
    body = {"provider": "openai", "api_key": "sk-test"}
    r = client.post("/api/brief/UNKN/stream", json=body)
    assert r.status_code == 404


def test_brief_stream_missing_key_400(client):
    """Body must include api_key. Pydantic rejects missing field."""
    r = client.post("/api/brief/AAPL/stream", json={"provider": "openai"})
    assert r.status_code == 422


def test_brief_stream_invalid_provider_400(client):
    body = {"provider": "ollama2", "api_key": "sk-test"}
    r = client.post("/api/brief/AAPL/stream", json=body)
    assert r.status_code == 422


def test_brief_stream_surfaces_llm_error_in_sse(client, monkeypatch):
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value=_make_row())
    monkeypatch.setattr(
        "alpha_agent.api.routes.brief.get_db_pool",
        AsyncMock(return_value=pool),
    )
    async def boom_stream(*args, **kwargs):
        raise RuntimeError("upstream LLM 429 rate limit")
        yield  # makes it a generator
    monkeypatch.setattr(
        "alpha_agent.api.routes.brief.stream_brief", boom_stream,
    )
    body = {"provider": "openai", "api_key": "sk-test"}
    with client.stream("POST", "/api/brief/AAPL/stream", json=body) as r:
        chunks = b"".join(r.iter_bytes()).decode()
    err_lines = [ln for ln in chunks.splitlines() if "error" in ln]
    assert any("rate limit" in ln for ln in err_lines)
    assert any('"type": "error"' in ln or "'type': 'error'" in ln for ln in err_lines)
