# tests/storage/test_migration_v012.py
import pytest

from alpha_agent.storage.postgres import close_pool, get_pool


@pytest.fixture
async def pool(applied_db):
    p = await get_pool(applied_db)
    yield p
    await close_pool()


@pytest.mark.asyncio
async def test_signal_weight_current_supports_live_and_shadow(pool):
    # A live + a shadow row for the SAME signal must coexist (PK widened to
    # (signal_name, status)). New columns default sanely.
    await pool.execute(
        "INSERT INTO signal_weight_current (signal_name, weight, last_updated, reason, status) "
        "VALUES ('news', 0.10, now(), 'ic_above_threshold', 'live')"
    )
    await pool.execute(
        "INSERT INTO signal_weight_current (signal_name, weight, last_updated, reason, status) "
        "VALUES ('news', 0.12, now(), 'shadow_candidate', 'shadow')"
    )
    rows = await pool.fetch(
        "SELECT status, weight, consecutive_bad_windows, shadow_streak "
        "FROM signal_weight_current WHERE signal_name='news' ORDER BY status"
    )
    assert {r["status"] for r in rows} == {"live", "shadow"}
    for r in rows:
        assert r["consecutive_bad_windows"] == 0
        assert r["shadow_streak"] == 0


@pytest.mark.asyncio
async def test_existing_rows_become_live(pool):
    # Insert WITHOUT status -> must default to 'live' (back-compat with the
    # Phase 1a writer that knew no status column).
    await pool.execute(
        "INSERT INTO signal_weight_current (signal_name, weight, last_updated, reason) "
        "VALUES ('macro', 0.07, now(), 'ic_above_threshold')"
    )
    status = await pool.fetchval(
        "SELECT status FROM signal_weight_current WHERE signal_name='macro'"
    )
    assert status == "live"
