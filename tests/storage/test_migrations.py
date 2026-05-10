import asyncpg
import pytest

pytestmark = pytest.mark.asyncio


async def test_apply_migrations_creates_all_tables(applied_db):
    conn = await asyncpg.connect(applied_db)
    try:
        rows = await conn.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname='public'"
        )
        names = {r["tablename"] for r in rows}
        assert names >= {
            "alert_queue",
            "cron_runs",
            "daily_signals_fast",
            "daily_signals_slow",
            "error_log",
        }
    finally:
        await conn.close()


async def test_alert_queue_has_dedup_unique_constraint(applied_db):
    conn = await asyncpg.connect(applied_db)
    try:
        row = await conn.fetchrow("""
            SELECT conname FROM pg_constraint
            WHERE conrelid = 'alert_queue'::regclass AND contype = 'u'
        """)
        assert row is not None, "alert_queue must have a UNIQUE constraint"
    finally:
        await conn.close()
