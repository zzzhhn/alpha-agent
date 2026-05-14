# tests/api/test_brief_stream_auth.py
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


def _signal_row():
    return {
        "ticker": "AAPL", "rating": "OW", "composite": 1.2,
        "breakdown": json.dumps({"breakdown": []}),
        "fetched_at": __import__("datetime").datetime(2026, 5, 14),
    }


def test_brief_stream_401_without_auth(client):
    r = client.post("/api/brief/AAPL/stream", json={})
    assert r.status_code == 401


def test_brief_stream_400_when_no_byok_key(client, monkeypatch):
    pool = MagicMock()
    pool.fetchrow = AsyncMock(side_effect=[_signal_row(), None])  # signal row, then no byok
    monkeypatch.setattr("alpha_agent.api.routes.brief.get_db_pool",
                        AsyncMock(return_value=pool))
    r = client.post("/api/brief/AAPL/stream", headers=_auth(), json={})
    assert r.status_code == 400
    assert "settings" in r.json()["detail"].lower()


def test_brief_stream_decrypts_byok_and_streams(client, monkeypatch):
    from alpha_agent.auth.crypto_box import encrypt
    ciphertext, nonce = encrypt("sk-real-user-key", _MASTER.encode())
    byok_row = {
        "provider": "openai", "ciphertext": ciphertext, "nonce": nonce,
        "model": "gpt-4o-mini", "base_url": None,
    }
    pool = MagicMock()
    pool.fetchrow = AsyncMock(side_effect=[_signal_row(), byok_row])
    pool.execute = AsyncMock()
    monkeypatch.setattr("alpha_agent.api.routes.brief.get_db_pool",
                        AsyncMock(return_value=pool))

    captured = {}

    async def fake_stream(*, provider, api_key, **kwargs):
        captured["provider"] = provider
        captured["api_key"] = api_key
        yield {"type": "summary", "delta": "ok"}
        yield {"type": "done"}

    monkeypatch.setattr("alpha_agent.api.routes.brief.stream_brief", fake_stream)
    with client.stream("POST", "/api/brief/AAPL/stream", headers=_auth(), json={}) as r:
        assert r.status_code == 200
        body = b"".join(r.iter_bytes()).decode()
    # The server decrypted the stored key and passed the plaintext to the streamer.
    assert captured["api_key"] == "sk-real-user-key"
    assert captured["provider"] == "openai"
    assert '"type": "done"' in body


def test_admin_refresh_401_without_auth(client):
    r = client.post("/api/admin/refresh", json={"job": "fast_intraday"})
    assert r.status_code == 401
