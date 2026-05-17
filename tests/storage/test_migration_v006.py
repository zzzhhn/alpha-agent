"""V006 migration test: impact_bucket + direction_bucket on news_items + macro_events.

Phase 6a Task 5 needs discrete LLM-as-Judge bucket columns so the news and
political_impact signals can run Tetlock-style impact * direction aggregation.
"""
import asyncpg
import pytest

from alpha_agent.storage.migrations.runner import apply_migrations

pytestmark = pytest.mark.asyncio


async def test_v006_adds_bucket_columns(test_db_url):
    applied = await apply_migrations(test_db_url)
    assert "V006__impact_direction_buckets" in applied

    conn = await asyncpg.connect(test_db_url)
    try:
        for table in ("news_items", "macro_events"):
            cols = {
                r["column_name"]
                for r in await conn.fetch(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema='public' AND table_name=$1",
                    table,
                )
            }
            assert "impact_bucket" in cols, f"{table} missing impact_bucket"
            assert "direction_bucket" in cols, f"{table} missing direction_bucket"
    finally:
        await conn.close()
