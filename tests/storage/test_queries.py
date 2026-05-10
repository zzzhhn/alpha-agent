import json
import pytest

from alpha_agent.storage.postgres import close_pool, get_pool
from alpha_agent.storage.queries import (
    insert_signal_slow,
    upsert_signal_fast,
    enqueue_alert,
    list_pending_alerts,
    mark_alert_dispatched,
    log_error,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def pool(applied_db):
    p = await get_pool(applied_db)
    yield p
    await close_pool()


async def test_insert_signal_slow_idempotent(pool):
    payload = {"breakdown": [{"signal": "factor", "z": 1.5}]}
    await insert_signal_slow(pool, "AAPL", "2026-05-10", 0.45, payload)
    # Same key must not raise — should UPDATE on conflict
    await insert_signal_slow(pool, "AAPL", "2026-05-10", 0.50, payload)
    row = await pool.fetchrow(
        "SELECT composite_partial FROM daily_signals_slow "
        "WHERE ticker=$1 AND date=$2::text::date", "AAPL", "2026-05-10"
    )
    assert row["composite_partial"] == 0.50  # second write wins


async def test_alert_dedup_within_30min_bucket(pool):
    bucket = 12345  # caller-computed
    await enqueue_alert(pool, "AAPL", "rating_change", {}, bucket)
    # same bucket → conflict ignored
    await enqueue_alert(pool, "AAPL", "rating_change", {}, bucket)
    rows = await pool.fetch(
        "SELECT id FROM alert_queue WHERE ticker='AAPL' AND type='rating_change'"
    )
    assert len(rows) == 1


async def test_list_pending_alerts_returns_only_undispatched(pool):
    await enqueue_alert(pool, "AAPL", "gap_3sigma", {}, 1)
    await enqueue_alert(pool, "MSFT", "gap_3sigma", {}, 1)
    pending = await list_pending_alerts(pool, limit=10)
    assert len(pending) == 2
    await mark_alert_dispatched(pool, pending[0]["id"])
    pending = await list_pending_alerts(pool, limit=10)
    assert len(pending) == 1


async def test_log_error_persists_with_context(pool):
    await log_error(pool, layer="signal", component="signals.news",
                    ticker="AAPL", err_type="TimeoutError", err_message="timeout",
                    context={"url": "https://..."})
    row = await pool.fetchrow("SELECT * FROM error_log ORDER BY id DESC LIMIT 1")
    assert row["component"] == "signals.news"
    assert json.loads(row["context"])["url"].startswith("https://")
