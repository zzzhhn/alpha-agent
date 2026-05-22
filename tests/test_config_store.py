# tests/test_config_store.py
import pytest

from alpha_agent import config_store
from alpha_agent.storage.postgres import close_pool, get_pool


@pytest.fixture
async def pool(applied_db):
    p = await get_pool(applied_db)
    yield p
    config_store._CACHE.clear()
    await close_pool()


def test_get_config_returns_default_when_cache_cold():
    config_store._CACHE.clear()
    assert config_store.get_config("rating.no_trade_band", 0.15) == 0.15
    assert config_store.get_config("does.not.exist") is None


@pytest.mark.asyncio
async def test_set_then_refresh_then_get(pool):
    config_store._CACHE.clear()
    await config_store.set_config(pool, "rating.no_trade_band", 0.20, user_id=0, source="test")
    await config_store.refresh_config(pool)
    assert config_store.get_config("rating.no_trade_band", 0.15) == pytest.approx(0.20)
    n = await pool.fetchval(
        "SELECT count(*) FROM config_change_log WHERE field = 'rating.no_trade_band'"
    )
    assert n >= 1


@pytest.mark.asyncio
async def test_object_valued_knob_roundtrips(pool):
    config_store._CACHE.clear()
    thresholds = {"buy": 1.4, "ow": 0.5, "hold": -0.5, "uw": -1.5}
    await config_store.set_config(pool, "rating.tier_thresholds", thresholds, user_id=0, source="test")
    await config_store.refresh_config(pool)
    assert config_store.get_config("rating.tier_thresholds", {})["buy"] == pytest.approx(1.4)
