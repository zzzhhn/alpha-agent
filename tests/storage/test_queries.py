import json
import asyncpg
import pytest

from alpha_agent.storage.postgres import close_pool, get_pool
from alpha_agent.storage.queries import (
    insert_signal_slow,
    enqueue_alert,
    list_pending_alerts,
    mark_alert_dispatched,
    log_error,
)

pytestmark = pytest.mark.asyncio


class _RaisingPool:
    """Stub pool whose execute() always raises DiskFullError — simulates the
    Neon free tier being full (the 2026-06-26 incident)."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def execute(self, *args, **kwargs):
        raise self._exc


async def test_log_error_never_raises_when_db_write_fails(capsys):
    """log_error is the diagnostic path handlers call to RECORD an upstream
    error. If its own INSERT raises (e.g. asyncpg.DiskFullError when the DB is
    full), it must NOT propagate — otherwise it masks the original error and
    turns it into an unhandled 500 (the cascade that flooded GH Actions with
    cron-failure emails). It must instead surface to stderr (never silently
    swallow — Silent Exception Anti-Pattern)."""
    pool = _RaisingPool(
        asyncpg.exceptions.DiskFullError("could not extend file ... 512 MB")
    )
    # Must return normally, not raise.
    await log_error(
        pool, layer="cron", component="news.macro",
        err_type="ValueError", err_message="upstream boom",
    )
    captured = capsys.readouterr()
    assert "log_error_failed" in captured.err
    assert "news.macro" in captured.err
    assert "DiskFullError" in captured.err


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
