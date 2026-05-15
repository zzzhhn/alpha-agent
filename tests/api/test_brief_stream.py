# tests/api/test_brief_stream.py
#
# Phase 4 rewrite: provider + api_key no longer live in the request body.
# Auth is required; BYOK is fetched server-side. Tests that relied on the
# body-key contract are updated to the new auth-aware contract.
import base64
import json
import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from jose import jwt

_SECRET = "test-secret-not-real-0123456789"
_MASTER = base64.b64encode(b"0123456789abcdef0123456789abcdef").decode()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("NEXTAUTH_SECRET", _SECRET)
    monkeypatch.setenv("BYOK_MASTER_KEY", _MASTER)
    from api.index import app
    return TestClient(app)


def _auth(sub="42"):
    now = int(time.time())
    tok = jwt.encode({"sub": sub, "iat": now, "exp": now + 3600},
                     _SECRET, algorithm="HS256")
    return {"Authorization": f"Bearer {tok}"}


def _make_row(ticker="AAPL"):
    # Shape matches the normalized row fetch_latest_signal selects:
    # ticker, score, rating, confidence, breakdown, fetched_at, partial.
    return {
        "ticker": ticker,
        "score": 1.42,
        "rating": "OW",
        "confidence": 0.85,
        "partial": False,
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


def _byok_row(provider="openai", model="gpt-4o-mini"):
    from alpha_agent.auth.crypto_box import encrypt
    ciphertext, nonce = encrypt("sk-test", _MASTER.encode())
    return {
        "provider": provider, "ciphertext": ciphertext, "nonce": nonce,
        "model": model, "base_url": None,
    }


def _pool_with_byok(signal_row=None, byok=None):
    """Return a mock pool that yields signal_row then byok_row on fetchrow calls."""
    pool = MagicMock()
    pool.fetchrow = AsyncMock(side_effect=[
        signal_row if signal_row is not None else _make_row(),
        byok if byok is not None else _byok_row(),
    ])
    pool.execute = AsyncMock()
    return pool


async def _fake_stream_tokens(**kwargs):
    """Mimics LiteLLM streaming chunk shape minimally."""
    for token in ["Apple", " is", " trading", " at", " 28.5x", "."]:
        yield {"type": "summary", "delta": token}
    yield {"type": "done"}


def test_brief_stream_emits_sse_deltas(client, monkeypatch):
    """SSE events are newline-delimited JSON with correct `data:` prefix."""
    pool = _pool_with_byok()
    monkeypatch.setattr(
        "alpha_agent.api.routes.brief.get_db_pool",
        AsyncMock(return_value=pool),
    )
    monkeypatch.setattr(
        "alpha_agent.api.routes.brief.stream_brief", _fake_stream_tokens,
    )
    with client.stream("POST", "/api/brief/AAPL/stream",
                       headers=_auth(), json={}) as r:
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
    r = client.post("/api/brief/UNKN/stream", headers=_auth(), json={})
    assert r.status_code == 404


def test_brief_stream_model_override_forwarded(client, monkeypatch):
    """model_override in the body is forwarded to stream_brief, taking
    precedence over the model stored in the byok row."""
    pool = _pool_with_byok()
    monkeypatch.setattr(
        "alpha_agent.api.routes.brief.get_db_pool",
        AsyncMock(return_value=pool),
    )
    captured = {}

    async def capture_stream(*, model, **kwargs):
        captured["model"] = model
        yield {"type": "done"}

    monkeypatch.setattr("alpha_agent.api.routes.brief.stream_brief", capture_stream)
    with client.stream("POST", "/api/brief/AAPL/stream",
                       headers=_auth(), json={"model_override": "gpt-4o"}) as r:
        assert r.status_code == 200
        b"".join(r.iter_bytes())
    assert captured["model"] == "gpt-4o"


def test_brief_stream_surfaces_llm_error_in_sse(client, monkeypatch):
    """LLM errors are surfaced as SSE error events, not HTTP 500."""
    pool = _pool_with_byok()
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
    with client.stream("POST", "/api/brief/AAPL/stream",
                       headers=_auth(), json={}) as r:
        chunks = b"".join(r.iter_bytes()).decode()
    err_lines = [ln for ln in chunks.splitlines() if "error" in ln]
    # N2 fix: raw str(e) is no longer forwarded to the client (key-leak risk).
    # The safe message includes only the exception class name, not the message text.
    assert any("RuntimeError" in ln for ln in err_lines)
    assert any('"type": "error"' in ln or "'type': 'error'" in ln for ln in err_lines)
