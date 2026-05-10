"""Tests for GET /api/stock/{ticker}."""
from __future__ import annotations

from datetime import date

import asyncpg


async def _seed(applied_db, ticker: str = "AAPL") -> None:
    conn = await asyncpg.connect(applied_db)
    try:
        await conn.execute(
            "INSERT INTO daily_signals_fast "
            "(ticker, date, composite, rating, confidence, breakdown, partial) "
            "VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7)",
            ticker,
            date.today(),
            1.23,
            "OW",
            0.72,
            '{"breakdown": []}',
            False,
        )
    finally:
        await conn.close()


async def test_stock_returns_full_card(client_with_db, applied_db):
    await _seed(applied_db)
    r = client_with_db.get("/api/stock/AAPL")
    assert r.status_code == 200
    body = r.json()
    assert body["card"]["ticker"] == "AAPL"
    assert body["card"]["rating"] == "OW"


async def test_stock_unknown_ticker_returns_404(client_with_db):
    r = client_with_db.get("/api/stock/NOTREAL")
    assert r.status_code == 404


async def test_stock_lowercase_ticker_normalized(client_with_db, applied_db):
    await _seed(applied_db, "MSFT")
    r = client_with_db.get("/api/stock/msft")
    assert r.status_code == 200
    assert r.json()["card"]["ticker"] == "MSFT"
