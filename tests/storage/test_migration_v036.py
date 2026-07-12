# tests/storage/test_migration_v036.py
import pytest
from alpha_agent.storage.migrations.runner import apply_migrations


@pytest.mark.asyncio
async def test_v036_creates_sim_tables(test_db_url):
    await apply_migrations(test_db_url)
    import asyncpg
    conn = await asyncpg.connect(test_db_url)
    try:
        tables = await conn.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename LIKE 'sim_%'"
        )
        names = {r["tablename"] for r in tables}
        assert "sim_account" in names
        assert "sim_order" in names
        assert "sim_position" in names
        assert "sim_equity_daily" in names
    finally:
        await conn.close()
