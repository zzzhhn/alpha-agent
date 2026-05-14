# tests/api/test_alpha_translate_auth.py
"""Auth + BYOK gate tests for POST /api/v1/alpha/translate (M5 E3b).

Mirrors the structure of test_brief_stream_auth.py.  The three cases:
  1. No Authorization header -> 401.
  2. Authenticated but no user_byok row -> 400 with "settings" in detail.
  3. Authenticated with encrypted key -> _build_byok_client receives the
     decrypted plaintext (assertion via monkeypatched _build_byok_client).
"""
import base64
import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from jose import jwt

_SECRET = "test-secret-not-real-0123456789"
_MASTER = base64.b64encode(b"0123456789abcdef0123456789abcdef").decode()

_VALID_BODY = {
    "text": "momentum: 20-day return cross-section rank",
    "universe": "SP500",
    "budget_tokens": 500,
}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("NEXTAUTH_SECRET", _SECRET)
    monkeypatch.setenv("BYOK_MASTER_KEY", _MASTER)
    from api.index import app
    return TestClient(app)


def _auth(sub="42"):
    now = int(time.time())
    tok = jwt.encode(
        {"sub": sub, "iat": now, "exp": now + 3600},
        _SECRET,
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {tok}"}


def test_alpha_translate_401_without_auth(client):
    """POST without Authorization header must return 401."""
    r = client.post("/api/v1/alpha/translate", json=_VALID_BODY)
    assert r.status_code == 401


def test_alpha_translate_400_when_no_byok_key(client, monkeypatch):
    """Authenticated request but no user_byok row -> 400 mentioning settings."""
    pool = MagicMock()
    # fetchrow returns None -> no BYOK key stored
    pool.fetchrow = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "alpha_agent.api.byok.get_db_pool",
        AsyncMock(return_value=pool),
    )
    r = client.post("/api/v1/alpha/translate", headers=_auth(), json=_VALID_BODY)
    assert r.status_code == 400
    assert "settings" in r.json()["detail"].lower()


def test_alpha_translate_decrypts_byok_and_builds_client(monkeypatch):
    """Server decrypts the stored BYOK row and passes plaintext to _build_byok_client.

    We monkeypatch _build_byok_client to capture the api_key arg and raise a
    sentinel so the test doesn't need a real LLM downstream. Uses
    raise_server_exceptions=False so the sentinel 500 is returned as an HTTP
    response rather than re-raised in test context.

    The required assertion is that api_key == "sk-real-user-key" (the plaintext).
    """
    monkeypatch.setenv("NEXTAUTH_SECRET", _SECRET)
    monkeypatch.setenv("BYOK_MASTER_KEY", _MASTER)
    from api.index import app
    from fastapi.testclient import TestClient as _TC
    no_raise_client = _TC(app, raise_server_exceptions=False)

    from alpha_agent.auth.crypto_box import encrypt

    ciphertext, nonce = encrypt("sk-real-user-key", _MASTER.encode())
    byok_row = {
        "provider": "openai",
        "ciphertext": ciphertext,
        "nonce": nonce,
        "model": "gpt-4o-mini",
        "base_url": None,
    }
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value=byok_row)
    monkeypatch.setattr(
        "alpha_agent.api.byok.get_db_pool",
        AsyncMock(return_value=pool),
    )

    captured = {}

    def fake_build(provider, api_key, api_base, model):
        captured["api_key"] = api_key
        captured["provider"] = provider
        # Raise HTTPException so FastAPI converts it to a structured response
        # rather than an unhandled 500.
        raise HTTPException(status_code=503, detail="sentinel - no real LLM needed")

    from fastapi import HTTPException
    monkeypatch.setattr("alpha_agent.api.byok._build_byok_client", fake_build)

    r = no_raise_client.post("/api/v1/alpha/translate", headers=_auth(), json=_VALID_BODY)
    # Key assertion: decrypted plaintext reached _build_byok_client.
    assert captured.get("api_key") == "sk-real-user-key", (
        f"Expected 'sk-real-user-key', got {captured.get('api_key')!r}"
    )
    assert captured.get("provider") == "openai"
    # 503 sentinel means we got past auth+decrypt successfully.
    assert r.status_code == 503
