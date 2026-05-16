import asyncpg
import pytest

pytestmark = pytest.mark.asyncio


async def test_v004_creates_news_items_and_macro_events(applied_db):
    conn = await asyncpg.connect(applied_db)
    try:
        rows = await conn.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname='public'"
        )
        names = {r["tablename"] for r in rows}
        assert "news_items" in names
        assert "macro_events" in names
    finally:
        await conn.close()


async def test_v004_news_items_has_dedup_unique_constraint(applied_db):
    conn = await asyncpg.connect(applied_db)
    try:
        row = await conn.fetchrow(
            "SELECT conname FROM pg_constraint "
            "WHERE conrelid = 'news_items'::regclass AND contype = 'u'"
        )
        assert row is not None
    finally:
        await conn.close()


async def test_v004_macro_events_tickers_extracted_is_text_array(applied_db):
    conn = await asyncpg.connect(applied_db)
    try:
        row = await conn.fetchrow(
            "SELECT data_type, udt_name FROM information_schema.columns "
            "WHERE table_name='macro_events' AND column_name='tickers_extracted'"
        )
        assert row["data_type"] == "ARRAY"
        assert row["udt_name"] == "_text"
    finally:
        await conn.close()


async def test_v004_macro_events_has_gin_index_on_tickers_extracted(applied_db):
    conn = await asyncpg.connect(applied_db)
    try:
        rows = await conn.fetch(
            "SELECT indexdef FROM pg_indexes WHERE tablename='macro_events'"
        )
        defs = " ".join(r["indexdef"] for r in rows)
        assert "using gin" in defs.lower()
        assert "tickers_extracted" in defs
    finally:
        await conn.close()


async def test_v004_idempotent(applied_db):
    """Re-applying migrations is a no-op (schema_migrations tracks state)."""
    from alpha_agent.storage.migrations.runner import apply_migrations
    second_run = await apply_migrations(applied_db)
    assert "V004__news_pipeline" not in second_run
