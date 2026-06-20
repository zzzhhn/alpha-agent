# tests/cron/test_l2_cycle.py
"""L2 cycle cron: thin wiring over the (separately-tested) driver. Verifies the
handler advances the book end-to-end, stamps cron_runs, and never raises."""
from datetime import UTC, date, datetime, timedelta

import asyncpg
import pytest

from alpha_agent.storage.product_ledger import RatingSnapshot, RunMeta, record_research_run

pytestmark = pytest.mark.asyncio


async def _seed(conn_url):
    conn = await asyncpg.connect(conn_url)
    try:
        start = date(2026, 6, 1)
        for i in range(12):
            d = start + timedelta(days=i)
            for tk, base in [("AAA", 100.0), ("BBB", 50.0), ("SPY", 500.0)]:
                await conn.execute(
                    "INSERT INTO daily_prices (ticker, date, close) VALUES ($1, $2, $3)",
                    tk, d, base * (1.0 + 0.01 * i),
                )
    finally:
        await conn.close()
    # complete gated runs via the ledger writer (own pool, closed each call).
    from alpha_agent.storage.postgres import close_pool, get_pool
    pool = await get_pool(conn_url)
    try:
        for d in (date(2026, 6, 1), date(2026, 6, 5), date(2026, 6, 9)):
            snaps = [RatingSnapshot(ticker=t, tier="BUY", rank=i + 1, eligible=True)
                     for i, t in enumerate(["AAA", "BBB"])]
            meta = RunMeta(scheduled_for_date=d, status="complete",
                           started_at=datetime(2026, 6, 1, tzinfo=UTC),
                           finished_at=datetime(2026, 6, 1, 1, tzinfo=UTC))
            await record_research_run(pool, meta, snaps)
    finally:
        await close_pool()


async def test_l2_cycle_handler_advances_and_logs(applied_db, monkeypatch):
    from alpha_agent.storage import postgres as pg_module
    pg_module._pool = None
    pg_module._pool_dsn = None
    monkeypatch.setenv("DATABASE_URL", applied_db)

    await _seed(applied_db)
    pg_module._pool = None
    pg_module._pool_dsn = None

    from api.cron.l2_cycle import handler
    result = await handler()

    assert result["ok"] is True
    assert result["error"] is None
    # default cadence is 5 trading days; the seed's runs are 4 days apart, so
    # only the 1st + 3rd qualify as rebalances (the 2nd is too soon).
    assert result["rebalances"] == 2

    conn = await asyncpg.connect(applied_db)
    try:
        run = await conn.fetchrow(
            "SELECT ok, details FROM cron_runs WHERE cron_name='l2_cycle' "
            "ORDER BY started_at DESC LIMIT 1"
        )
        assert run is not None and run["ok"] is True
        eq = await conn.fetchval("SELECT count(*) FROM l2_equity_daily")
        assert eq == 1  # one completed holding period (1st batch -> 3rd batch fill)
    finally:
        await conn.close()
