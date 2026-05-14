# tests/auth/test_dependencies.py
import time

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from jose import jwt

from alpha_agent.auth.dependencies import require_user

_SECRET = "test-secret-not-real-0123456789"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("NEXTAUTH_SECRET", _SECRET)
    app = FastAPI()

    @app.get("/whoami")
    async def whoami(user_id: int = Depends(require_user)) -> dict:
        return {"user_id": user_id}

    return TestClient(app)


def _token(sub="42", **overrides) -> str:
    now = int(time.time())
    payload = {"sub": sub, "iat": now, "exp": now + 3600}
    payload.update(overrides)
    return jwt.encode(payload, _SECRET, algorithm="HS256")


def test_require_user_returns_user_id(client):
    r = client.get("/whoami", headers={"Authorization": f"Bearer {_token()}"})
    assert r.status_code == 200
    assert r.json() == {"user_id": 42}


def test_require_user_401_on_missing_header(client):
    r = client.get("/whoami")
    assert r.status_code == 401


def test_require_user_401_on_non_bearer(client):
    r = client.get("/whoami", headers={"Authorization": "Basic abc"})
    assert r.status_code == 401


def test_require_user_401_on_invalid_jwt(client):
    r = client.get("/whoami", headers={"Authorization": "Bearer not.a.jwt"})
    assert r.status_code == 401


def test_require_user_401_on_expired_jwt(client):
    expired = _token(exp=int(time.time()) - 10)
    r = client.get("/whoami", headers={"Authorization": f"Bearer {expired}"})
    assert r.status_code == 401


def test_require_user_401_on_non_numeric_sub(client):
    bad = _token(sub="not-a-number")
    r = client.get("/whoami", headers={"Authorization": f"Bearer {bad}"})
    assert r.status_code == 401
