"""Tests for GET /api/picks/lean."""
from __future__ import annotations

from datetime import date

import asyncpg


async def _seed_fast_rows(applied_db, n: int = 5) -> None:
    conn = await asyncpg.connect(applied_db)
    today = date.today()
    try:
        ratings = ["BUY", "OW", "HOLD", "UW", "SELL"]
        for i, rating in enumerate(ratings[:n]):
            await conn.execute(
                "INSERT INTO daily_signals_fast "
                "(ticker, date, composite, rating, confidence, breakdown, partial) "
                "VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7)",
                f"T{i}",
                today,
                2.0 - 0.5 * i,
                rating,
                0.8,
                '{"breakdown": []}',
                False,
            )
    finally:
        await conn.close()


async def test_picks_lean_returns_sorted_by_composite(client_with_db, applied_db):
    await _seed_fast_rows(applied_db, n=5)
    r = client_with_db.get("/api/picks/lean?limit=20")
    assert r.status_code == 200
    body = r.json()
    assert "picks" in body
    composites = [p["composite_score"] for p in body["picks"]]
    assert composites == sorted(composites, reverse=True)


async def test_picks_lean_respects_limit(client_with_db, applied_db):
    await _seed_fast_rows(applied_db, n=5)
    r = client_with_db.get("/api/picks/lean?limit=2")
    assert r.status_code == 200
    assert len(r.json()["picks"]) == 2


async def test_picks_lean_empty_db_returns_empty_list(client_with_db):
    r = client_with_db.get("/api/picks/lean")
    assert r.status_code == 200
    body = r.json()
    assert body["picks"] == []
    assert body["stale"] is False
