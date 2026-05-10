"""Tests for POST /api/brief/{ticker}."""
from __future__ import annotations

from datetime import date

import asyncpg


async def _seed(applied_db: str) -> None:
    conn = await asyncpg.connect(applied_db)
    try:
        await conn.execute(
            "INSERT INTO daily_signals_fast "
            "(ticker, date, composite, rating, confidence, breakdown, partial) "
            "VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7)",
            "AAPL",
            date.today(),
            1.23,
            "OW",
            0.72,
            '{"breakdown":[{"signal":"factor","z":1.8,"weight":0.30,'
            '"weight_effective":0.30,"contribution":0.54,"raw":1.8,'
            '"source":"factor_engine",'
            '"timestamp":"2024-01-01T00:00:00+00:00","error":null}]}',
            False,
        )
    finally:
        await conn.close()


async def test_brief_lean_mode_returns_thesis(client_with_db, applied_db):
    await _seed(applied_db)
    r = client_with_db.post("/api/brief/AAPL", json={"mode": "lean"})
    assert r.status_code == 200
    body = r.json()
    assert "thesis" in body
    assert "bull" in body["thesis"] and "bear" in body["thesis"]
    assert isinstance(body["thesis"]["bull"], list)


async def test_brief_rich_mode_returns_501_in_m2(client_with_db, applied_db):
    """Rich BYOK LLM is M3; M2 stub returns 501 Not Implemented."""
    await _seed(applied_db)
    r = client_with_db.post(
        "/api/brief/AAPL",
        json={"mode": "rich", "llm_provider": "anthropic", "api_key": "sk-test"},
    )
    assert r.status_code == 501


async def test_brief_unknown_ticker_returns_404(client_with_db):
    r = client_with_db.post("/api/brief/NOTREAL", json={"mode": "lean"})
    assert r.status_code == 404
