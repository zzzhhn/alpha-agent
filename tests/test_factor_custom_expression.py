import pytest

from alpha_agent.config_store import DEFAULTS, _CACHE, get_config, refresh_config, set_config
from alpha_agent.storage.postgres import close_pool, get_pool


@pytest.fixture
async def pool(applied_db):
    p = await get_pool(applied_db)
    yield p
    await close_pool()


def test_custom_expression_default_is_none():
    """Forgiveness: default of None means the knob is opt-in and the existing
    factor.mode preset path stays in effect when nothing is approved yet."""
    assert "factor.custom_expression" in DEFAULTS
    assert DEFAULTS["factor.custom_expression"] is None


@pytest.mark.asyncio
async def test_set_then_refresh_then_get(pool):
    _CACHE.clear()
    await set_config(pool, "factor.custom_expression", "rank(ts_mean(returns, 8))",
                     user_id=0, source="test")
    await refresh_config(pool)
    assert get_config("factor.custom_expression") == "rank(ts_mean(returns, 8))"


@pytest.mark.asyncio
async def test_set_to_none_restores_default_path(pool):
    """Reversibility: setting back to None means the preset path resumes."""
    _CACHE.clear()
    await set_config(pool, "factor.custom_expression", "rank(returns)",
                     user_id=0, source="test")
    await refresh_config(pool)
    assert get_config("factor.custom_expression") == "rank(returns)"
    await set_config(pool, "factor.custom_expression", None, user_id=0, source="test")
    await refresh_config(pool)
    assert get_config("factor.custom_expression") is None
