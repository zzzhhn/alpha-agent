# tests/api/test_paper_routes.py
import base64
import time
import pytest
from fastapi.testclient import TestClient
from jose import jwt
from unittest.mock import AsyncMock, MagicMock

_SECRET = "test-secret-not-real-0123456789"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("NEXTAUTH_SECRET", _SECRET)
    monkeypatch.setenv("BYOK_MASTER_KEY", base64.b64encode(b"0" * 32).decode())
    from api.index import app
    return TestClient(app)


def _auth(sub: str = "7") -> dict:
    now = int(time.time())
    tok = jwt.encode(
        {"sub": sub, "iat": now, "exp": now + 3600},
        _SECRET, algorithm="HS256",
    )
    return {"Authorization": f"Bearer {tok}"}


def _mock_pool(monkeypatch, fetchrow_val=None, fetch_val=None, fetchval_val=None):
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value=fetchrow_val)
    pool.fetch = AsyncMock(return_value=fetch_val or [])
    pool.fetchval = AsyncMock(return_value=fetchval_val)
    pool.execute = AsyncMock()
    monkeypatch.setattr("alpha_agent.api.routes.paper.get_db_pool", AsyncMock(return_value=pool))
    return pool


def test_account_requires_auth(client):
    assert client.get("/api/paper/account").status_code == 401


def test_account_auto_creates_and_returns(client, monkeypatch):
    import datetime
    account_row = {
        "id": 1, "user_id": 7, "initial_cash": 1000000.0,
        "cash": 1000000.0, "reset_count": 0, "created_at": datetime.datetime.now(),
        "reset_at": None,
    }
    pool = _mock_pool(monkeypatch, fetchrow_val=account_row, fetch_val=[], fetchval_val=None)
    r = client.get("/api/paper/account", headers=_auth())
    assert r.status_code == 200
    body = r.json()
    assert body["cash"] == 1000000.0
    assert body["positions"] == []


def test_place_market_order_returns_201(client, monkeypatch):
    import datetime
    account_row = {
        "id": 1, "user_id": 7, "initial_cash": 1000000.0,
        "cash": 1000000.0, "reset_count": 0,
        "created_at": datetime.datetime.now(), "reset_at": None,
    }
    pool = _mock_pool(monkeypatch, fetchrow_val=account_row, fetchval_val=42)
    r = client.post(
        "/api/paper/order",
        headers=_auth(),
        json={"ticker": "AAPL", "side": "buy", "order_type": "market", "qty": 10},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "pending"
    assert body["order_id"] == 42


def test_place_limit_order_requires_limit_price(client, monkeypatch):
    import datetime
    account_row = {
        "id": 1, "user_id": 7, "initial_cash": 1000000.0,
        "cash": 1000000.0, "reset_count": 0,
        "created_at": datetime.datetime.now(), "reset_at": None,
    }
    _mock_pool(monkeypatch, fetchrow_val=account_row)
    r = client.post(
        "/api/paper/order",
        headers=_auth(),
        json={"ticker": "AAPL", "side": "buy", "order_type": "limit", "qty": 10},
    )
    assert r.status_code == 400


def test_cancel_order_sets_cancelled(client, monkeypatch):
    import datetime
    order_row = {
        "id": 5, "account_id": 1, "status": "pending",
        "created_at": datetime.datetime.now(),
    }
    account_row = {
        "id": 1, "user_id": 7, "initial_cash": 1000000.0,
        "cash": 1000000.0, "reset_count": 0,
        "created_at": datetime.datetime.now(), "reset_at": None,
    }
    pool = _mock_pool(monkeypatch, fetchrow_val=account_row)
    pool.fetchrow = AsyncMock(side_effect=[account_row, order_row])
    r = client.delete("/api/paper/order/5", headers=_auth())
    assert r.status_code == 204


def test_equity_curve_returns_series(client, monkeypatch):
    import datetime
    account_row = {
        "id": 1, "user_id": 7, "initial_cash": 1000000.0,
        "cash": 1000000.0, "reset_count": 0,
        "created_at": datetime.datetime.now(), "reset_at": None,
    }
    equity_rows = [
        {"as_of_date": datetime.date(2026, 7, 1), "portfolio_value": 1000000.0,
         "benchmark_close": 540.0},
        {"as_of_date": datetime.date(2026, 7, 2), "portfolio_value": 1010000.0,
         "benchmark_close": 543.0},
    ]
    pool = _mock_pool(monkeypatch, fetchrow_val=account_row, fetch_val=equity_rows)
    r = client.get("/api/paper/equity-curve", headers=_auth())
    assert r.status_code == 200
    body = r.json()
    assert len(body["series"]) == 2
    assert body["series"][0]["benchmark_index"] == pytest.approx(100.0)
    assert body["series"][1]["benchmark_index"] > 100.0


def test_reset_clears_positions_restores_cash(client, monkeypatch):
    import datetime
    account_row = {
        "id": 1, "user_id": 7, "initial_cash": 1000000.0,
        "cash": 800000.0, "reset_count": 0,
        "created_at": datetime.datetime.now(), "reset_at": None,
    }
    pool = _mock_pool(monkeypatch, fetchrow_val=account_row, fetch_val=[])
    r = client.post("/api/paper/reset", headers=_auth())
    assert r.status_code == 200
    body = r.json()
    assert body["cash"] == 1000000.0
    assert body["reset_count"] == 1
