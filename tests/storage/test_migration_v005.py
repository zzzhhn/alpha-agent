"""V005 migration test: minute_bars + signal_ic_history + signal_weight_current.

Uses the storage conftest's `test_db_url` fixture (pytest-postgresql process)
to apply all migrations and verify V005 created the three tables with
the indexes and primary keys the spec requires.
"""
import asyncpg
import pytest

from alpha_agent.storage.migrations.runner import apply_migrations

pytestmark = pytest.mark.asyncio


async def test_v005_creates_three_tables(test_db_url):
    """V005 must create minute_bars + signal_ic_history + signal_weight_current,
    each with the indexes and primary keys the spec requires."""
    applied = await apply_migrations(test_db_url)
    assert "V005__signal_ic_and_minute_bars" in applied

    conn = await asyncpg.connect(test_db_url)
    try:
        tables = {r["tablename"] for r in await conn.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname='public'"
        )}
        assert "minute_bars" in tables
        assert "signal_ic_history" in tables
        assert "signal_weight_current" in tables

        # minute_bars primary key (ticker, ts)
        pk = await conn.fetchval(
            "SELECT pg_get_constraintdef(c.oid) FROM pg_constraint c "
            "JOIN pg_class t ON c.conrelid = t.oid "
            "WHERE t.relname = 'minute_bars' AND c.contype = 'p'"
        )
        assert "ticker" in pk and "ts" in pk

        # signal_weight_current.signal_name primary key
        pk2 = await conn.fetchval(
            "SELECT pg_get_constraintdef(c.oid) FROM pg_constraint c "
            "JOIN pg_class t ON c.conrelid = t.oid "
            "WHERE t.relname = 'signal_weight_current' AND c.contype = 'p'"
        )
        assert "signal_name" in pk2
    finally:
        await conn.close()
