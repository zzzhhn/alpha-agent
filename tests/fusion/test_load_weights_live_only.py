# tests/fusion/test_load_weights_live_only.py
import pytest

from alpha_agent.fusion.combine import load_weights
from alpha_agent.storage.postgres import close_pool, get_pool


@pytest.fixture
async def pool(applied_db):
    p = await get_pool(applied_db)
    yield p
    await close_pool()


@pytest.mark.asyncio
async def test_load_weights_ignores_shadow_rows(pool):
    await pool.execute(
        "INSERT INTO signal_weight_current (signal_name, weight, last_updated, reason, status) "
        "VALUES ('news', 0.10, now(), 'live', 'live')"
    )
    await pool.execute(
        "INSERT INTO signal_weight_current (signal_name, weight, last_updated, reason, status) "
        "VALUES ('news', 0.99, now(), 'shadow_candidate', 'shadow')"
    )
    weights = await load_weights(pool)
    assert weights["news"] == pytest.approx(0.10)  # NOT the 0.99 shadow
