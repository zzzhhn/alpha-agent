# tests/storage/test_daily_prices_queries.py
import pytest

from alpha_agent.storage.postgres import close_pool, get_pool
from alpha_agent.storage.queries import upsert_daily_close


@pytest.fixture
async def pool(applied_db):
    p = await get_pool(applied_db)
    yield p
    await close_pool()


@pytest.mark.asyncio
async def test_upsert_daily_close_inserts_and_replaces(pool):
    await upsert_daily_close(pool, "MSFT", "2026-01-05", 410.0)
    await upsert_daily_close(pool, "MSFT", "2026-01-05", 415.0)  # same PK
    row = await pool.fetchrow(
        "SELECT close FROM daily_prices WHERE ticker = 'MSFT' AND date = '2026-01-05'"
    )
    assert row["close"] == pytest.approx(415.0)


@pytest.mark.asyncio
async def test_upsert_daily_close_skips_nonpositive(pool):
    # A zero/negative close is bad data (yfinance gap); the helper must skip it.
    await upsert_daily_close(pool, "NVDA", "2026-01-06", 0.0)
    row = await pool.fetchrow(
        "SELECT close FROM daily_prices WHERE ticker = 'NVDA' AND date = '2026-01-06'"
    )
    assert row is None
