"""Alert dispatcher cron tests. Uses real Postgres (applied_db fixture)."""
import asyncpg
import pytest

pytestmark = pytest.mark.asyncio


async def test_dispatcher_marks_pending_alerts_dispatched(applied_db, monkeypatch):
    from alpha_agent.storage import postgres as pg_module

    pg_module._pool = None
    pg_module._pool_dsn = None

    monkeypatch.setenv("DATABASE_URL", applied_db)

    conn = await asyncpg.connect(applied_db)
    try:
        for i in range(3):
            await conn.execute(
                "INSERT INTO alert_queue (ticker, type, payload, dedup_bucket) "
                "VALUES ($1, $2, $3::jsonb, $4)",
                f"T{i}",
                "rating_change",
                '{"to": "OW"}',
                1000 + i,
            )
    finally:
        await conn.close()

    from api.cron.alert_dispatcher import handler

    result = await handler()
    assert result["ok"] is True
    assert result["dispatched_count"] == 3

    conn = await asyncpg.connect(applied_db)
    try:
        pending = await conn.fetchval(
            "SELECT COUNT(*) FROM alert_queue WHERE dispatched=false"
        )
        assert pending == 0
    finally:
        await conn.close()


async def test_dispatcher_handles_empty_queue(applied_db, monkeypatch):
    from alpha_agent.storage import postgres as pg_module

    pg_module._pool = None
    pg_module._pool_dsn = None

    monkeypatch.setenv("DATABASE_URL", applied_db)

    from api.cron.alert_dispatcher import handler

    result = await handler()
    assert result["ok"] is True
    assert result["dispatched_count"] == 0
