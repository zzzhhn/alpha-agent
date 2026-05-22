# tests/storage/test_migration_v014.py
import json

import pytest

from alpha_agent.storage.postgres import close_pool, get_pool


@pytest.fixture
async def pool(applied_db):
    p = await get_pool(applied_db)
    yield p
    await close_pool()


@pytest.mark.asyncio
async def test_engine_config_upserts(pool):
    await pool.execute(
        "INSERT INTO engine_config (key, value, updated_by) VALUES ($1, $2::jsonb, 0) "
        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
        "rating.no_trade_band", json.dumps(0.15),
    )
    await pool.execute(
        "INSERT INTO engine_config (key, value, updated_by) VALUES ($1, $2::jsonb, 0) "
        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
        "rating.no_trade_band", json.dumps(0.20),
    )
    row = await pool.fetchrow("SELECT value FROM engine_config WHERE key = 'rating.no_trade_band'")
    assert json.loads(row["value"]) == pytest.approx(0.20)
