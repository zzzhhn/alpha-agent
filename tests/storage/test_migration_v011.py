# tests/storage/test_migration_v011.py
#
# Fixture note: `applied_db` (from tests/storage/conftest.py) is a DSN STRING
# with all migrations applied, NOT a pool. The established pattern is to build
# a pool via get_pool(applied_db) (see tests/backtest/test_ic_engine.py) or to
# connect with asyncpg directly (see tests/storage/test_migration_v006.py).
import pytest

from alpha_agent.storage.postgres import close_pool, get_pool


@pytest.fixture
async def pool(applied_db):
    p = await get_pool(applied_db)
    yield p
    await close_pool()


@pytest.mark.asyncio
async def test_daily_prices_table_exists_and_upserts(pool):
    await pool.execute(
        """
        INSERT INTO daily_prices (ticker, date, close)
        VALUES ('AAPL', '2026-01-02', 185.5)
        ON CONFLICT (ticker, date) DO UPDATE SET close = EXCLUDED.close
        """
    )
    # Upsert (same PK) must replace, not error.
    await pool.execute(
        """
        INSERT INTO daily_prices (ticker, date, close)
        VALUES ('AAPL', '2026-01-02', 190.0)
        ON CONFLICT (ticker, date) DO UPDATE SET close = EXCLUDED.close
        """
    )
    row = await pool.fetchrow(
        "SELECT close FROM daily_prices WHERE ticker = 'AAPL' AND date = '2026-01-02'"
    )
    assert row["close"] == pytest.approx(190.0)
