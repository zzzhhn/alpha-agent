# tests/api/test_stock_ohlcv.py
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from api.index import app
    return TestClient(app)


def _ohlcv_df():
    return pd.DataFrame(
        {"Open": [100.0, 101.0], "High": [102.0, 103.0],
         "Low": [99.0, 100.5], "Close": [101.5, 102.5],
         "Volume": [1_000_000, 1_100_000]},
        index=pd.DatetimeIndex(["2026-05-12", "2026-05-13"]),
    )


def test_ohlcv_returns_bars(client):
    m = MagicMock()
    m.history.return_value = _ohlcv_df()
    with patch("alpha_agent.api.routes.stock.get_ticker", return_value=m):
        r = client.get("/api/stock/AAPL/ohlcv?period=6mo")
    assert r.status_code == 200
    body = r.json()
    assert body["ticker"] == "AAPL"
    assert body["period"] == "6mo"
    assert len(body["bars"]) == 2
    assert body["bars"][0] == {
        "date": "2026-05-12", "open": 100.0, "high": 102.0,
        "low": 99.0, "close": 101.5, "volume": 1_000_000,
    }


def test_ohlcv_empty_returns_empty_bars(client):
    m = MagicMock()
    m.history.return_value = pd.DataFrame()
    with patch("alpha_agent.api.routes.stock.get_ticker", return_value=m):
        r = client.get("/api/stock/UNKN/ohlcv")
    assert r.status_code == 200
    assert r.json()["bars"] == []


def test_ohlcv_invalid_period_rejected(client):
    """Pydantic Query validation should reject periods outside the allowed set."""
    r = client.get("/api/stock/AAPL/ohlcv?period=99y")
    assert r.status_code == 422
