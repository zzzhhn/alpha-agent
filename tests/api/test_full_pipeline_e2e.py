"""M2 acceptance: full pipeline e2e — DB seeded (as cron writes) -> API reads -> schema validates.

Two tests:
1. test_full_pipeline — seeds daily_signals_fast for AAPL+MSFT, then verifies
   all four M2 API endpoints (/picks/lean, /stock, /brief, /_health) return
   correct shapes and values.
2. test_health_endpoints_after_cron — seeds cron_runs, verifies /api/_health/cron
   surfaces the run with ok=True.

Uses httpx.AsyncClient + ASGITransport to keep all DB and HTTP calls in the
same asyncio event loop, avoiding the asyncpg "attached to a different loop"
error that arises when mixing pytest-asyncio await with starlette TestClient.
"""
from __future__ import annotations

from datetime import UTC, datetime

import asyncpg
import httpx
import pytest

from alpha_agent.api.app import create_app

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _seed_fast_rows(dsn: str, tickers: list[str]) -> None:
    """Seed daily_signals_fast rows directly via asyncpg (no pool singleton)."""
    today = datetime.now(UTC).date().isoformat()
    conn = await asyncpg.connect(dsn)
    try:
        for i, ticker in enumerate(tickers):
            await conn.execute(
                "INSERT INTO daily_signals_fast "
                "(ticker, date, composite, rating, confidence, breakdown, partial) "
                "VALUES ($1, $2::text::date, $3, $4, $5, $6::jsonb, $7) "
                "ON CONFLICT (ticker, date) DO NOTHING",
                ticker,
                today,
                # Give AAPL a higher composite so sort order is deterministic.
                1.5 - i * 0.1,
                "OW",
                0.85,
                '{"breakdown":[{"signal":"factor","z":1.5,"weight":0.30,'
                '"weight_effective":0.30,"contribution":0.45,"raw":1.5,'
                '"source":"factor_engine",'
                '"timestamp":"2024-01-01T00:00:00+00:00","error":null}]}',
                False,
            )
    finally:
        await conn.close()


async def _seed_cron_run(dsn: str, cron_name: str) -> None:
    """Seed a cron_runs row directly via asyncpg (no pool singleton)."""
    now = datetime.now(UTC)
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(
            "INSERT INTO cron_runs "
            "(cron_name, started_at, finished_at, ok, error_count, details) "
            "VALUES ($1, $2, $3, $4, $5, $6::jsonb)",
            cron_name,
            now,
            now,
            True,
            0,
            '{"rows_written": 2}',
        )
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

async def test_full_pipeline(applied_db, monkeypatch):
    """Seed DB (simulating what fast_intraday cron writes) then verify:
    1. /api/picks/lean returns 2 cards sorted by composite DESC
    2. /api/stock/AAPL returns full card with correct ticker and valid rating
    3. /api/brief/AAPL Lean returns thesis dict with bull/bear lists
    """
    monkeypatch.setenv("DATABASE_URL", applied_db)
    import alpha_agent.storage.postgres as pg_module
    pg_module._pool = None
    pg_module._pool_dsn = None

    await _seed_fast_rows(applied_db, ["AAPL", "MSFT"])

    # Reset pool so the httpx client creates it fresh in this event loop.
    pg_module._pool = None
    pg_module._pool_dsn = None

    app = create_app()
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. /api/picks/lean
        r = await ac.get("/api/picks/lean?limit=10")
        assert r.status_code == 200
        body = r.json()
        assert len(body["picks"]) == 2
        assert {p["ticker"] for p in body["picks"]} == {"AAPL", "MSFT"}
        composites = [p["composite_score"] for p in body["picks"]]
        assert composites == sorted(composites, reverse=True)

        # 2. /api/stock/AAPL
        r = await ac.get("/api/stock/AAPL")
        assert r.status_code == 200
        card = r.json()["card"]
        assert card["ticker"] == "AAPL"
        assert card["rating"] in {"BUY", "OW", "HOLD", "UW", "SELL"}

        # 3. /api/brief/AAPL Lean
        r = await ac.post("/api/brief/AAPL", json={"mode": "lean"})
        assert r.status_code == 200
        thesis = r.json()["thesis"]
        assert "bull" in thesis
        assert "bear" in thesis
        assert isinstance(thesis["bull"], list)
        assert isinstance(thesis["bear"], list)

    pg_module._pool = None
    pg_module._pool_dsn = None


async def test_health_endpoints_after_cron(applied_db, monkeypatch):
    """After a cron_runs row is present, /api/_health/cron should surface it."""
    monkeypatch.setenv("DATABASE_URL", applied_db)
    import alpha_agent.storage.postgres as pg_module
    pg_module._pool = None
    pg_module._pool_dsn = None

    await _seed_cron_run(applied_db, "fast_intraday")

    app = create_app()
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/api/_health/cron")
        assert r.status_code == 200
        runs = r.json()["cron"]["fast_intraday"]
        assert len(runs) >= 1
        assert runs[0]["ok"] is True

    pg_module._pool = None
    pg_module._pool_dsn = None
