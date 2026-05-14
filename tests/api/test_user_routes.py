# tests/api/test_user_routes.py
import base64
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
    tok = jwt.encode(
        {"sub": sub, "iat": now, "exp": now + 3600, "email": "u@example.com"},
        _SECRET, algorithm="HS256",
    )
    return {"Authorization": f"Bearer {tok}"}


def test_get_me_requires_auth(client):
    assert client.get("/api/user/me").status_code == 401


def test_get_me_with_auth(client, monkeypatch):
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value={
        "id": 42, "email": "u@example.com",
        "created_at": __import__("datetime").datetime(2026, 5, 14),
    })
    pool.fetchval = AsyncMock(return_value=False)  # has_byok
    monkeypatch.setattr("alpha_agent.api.routes.user.get_db_pool",
                        AsyncMock(return_value=pool))
    r = client.get("/api/user/me", headers=_auth())
    assert r.status_code == 200
    body = r.json()
    assert body["user_id"] == 42
    assert body["email"] == "u@example.com"
    assert body["has_byok"] is False


def test_post_byok_encrypts_and_stores(client, monkeypatch):
    pool = MagicMock()
    pool.execute = AsyncMock()
    monkeypatch.setattr("alpha_agent.api.routes.user.get_db_pool",
                        AsyncMock(return_value=pool))
    r = client.post(
        "/api/user/byok",
        headers=_auth(),
        json={"provider": "openai", "api_key": "sk-secret-tail1234", "model": "gpt-4o-mini"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["provider"] == "openai"
    assert body["last4"] == "1234"
    # The plaintext key must NEVER be echoed back.
    assert "api_key" not in body
    assert "sk-secret" not in r.text
    # The INSERT call must carry ciphertext bytes, not the plaintext.
    insert_sql = pool.execute.call_args.args[0]
    assert "INSERT INTO user_byok" in insert_sql
    assert b"sk-secret-tail1234" not in pool.execute.call_args.args


def test_get_byok_returns_last4_only(client, monkeypatch):
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value={
        "provider": "openai", "last4": "1234", "model": "gpt-4o-mini",
        "base_url": None, "encrypted_at": __import__("datetime").datetime(2026, 5, 14),
        "last_used_at": None,
    })
    monkeypatch.setattr("alpha_agent.api.routes.user.get_db_pool",
                        AsyncMock(return_value=pool))
    r = client.get("/api/user/byok", headers=_auth())
    assert r.status_code == 200
    body = r.json()
    assert body["last4"] == "1234"
    assert "ciphertext" not in body
    assert "api_key" not in body


def test_get_byok_404_when_none(client, monkeypatch):
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value=None)
    monkeypatch.setattr("alpha_agent.api.routes.user.get_db_pool",
                        AsyncMock(return_value=pool))
    r = client.get("/api/user/byok", headers=_auth())
    assert r.status_code == 404


def test_delete_account_cascades(client, monkeypatch):
    pool = MagicMock()
    pool.execute = AsyncMock(return_value="DELETE 1")
    monkeypatch.setattr("alpha_agent.api.routes.user.get_db_pool",
                        AsyncMock(return_value=pool))
    r = client.post("/api/user/account/delete", headers=_auth())
    assert r.status_code == 204
    # A single DELETE FROM users relies on ON DELETE CASCADE for the rest.
    assert "DELETE FROM users" in pool.execute.call_args.args[0]
