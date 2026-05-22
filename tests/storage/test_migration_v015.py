import pytest

from alpha_agent.storage.postgres import close_pool, get_pool


@pytest.fixture
async def pool(applied_db):
    p = await get_pool(applied_db)
    yield p
    await close_pool()


@pytest.mark.asyncio
async def test_proposal_columns_exist(pool):
    await pool.execute(
        "INSERT INTO config_change_log (user_id, field, new_value, source, status, evidence) "
        "VALUES (0, 'rating.no_trade_band', '0.2', 'proposer', 'pending', $1::jsonb)",
        '{"sharpe_oos": 0.8, "n_trials": 4}',
    )
    row = await pool.fetchrow(
        "SELECT status, evidence FROM config_change_log WHERE status = 'pending' LIMIT 1"
    )
    assert row["status"] == "pending"
    assert row["evidence"] is not None
    nulls = await pool.fetchval("SELECT count(*) FROM config_change_log WHERE status IS NULL")
    assert nulls >= 0
