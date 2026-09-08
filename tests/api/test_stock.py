"""Tests for GET /api/stock/{ticker}."""
from __future__ import annotations

from datetime import date

import asyncpg
import json


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
    assert set(body["card"]["dimension_scores"]) == {
        "Momentum", "Technical", "Sentiment", "Catalyst", "Insider", "Flow",
    }


async def test_stock_unknown_ticker_returns_404(client_with_db):
    r = client_with_db.get("/api/stock/NOTREAL")
    assert r.status_code == 404


async def test_stock_lowercase_ticker_normalized(client_with_db, applied_db):
    await _seed(applied_db, "MSFT")
    r = client_with_db.get("/api/stock/msft")
    assert r.status_code == 200
    assert r.json()["card"]["ticker"] == "MSFT"


async def test_hot_projection_preserves_observations_and_flags(applied_db):
    from alpha_agent.api.signal_lookup import fetch_latest_signal

    await _seed(applied_db)
    observation = {"signal": "factor", "z": 1.0, "raw": {"z_long": 0.5}}
    envelope = {
        "breakdown": [observation], "tier_flip_today": True,
        "gex_info": {"regime": "pinned"}, "research_attachment": "x" * 10000,
    }
    conn = await asyncpg.connect(applied_db)
    try:
        await conn.execute("UPDATE daily_signals_fast SET breakdown=$1::jsonb", json.dumps(envelope))
        signal = await fetch_latest_signal(conn, "AAPL")
        assert signal["breakdown"] == [observation]
        assert signal["tier_flip_today"] is True
        assert signal["gex_info"] == {"regime": "pinned"}
        # Query projection is not destructive storage cleanup.
        assert await conn.fetchval("SELECT length(breakdown->>'research_attachment') FROM daily_signals_fast") == 10000
    finally:
        await conn.close()
