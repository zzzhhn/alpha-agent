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


from alpha_agent.signals.factor import (
    LONG_TERM_FACTOR_EXPR,
    SHORT_TERM_FACTOR_EXPR,
    _resolve_default_expr,
)


def test_resolver_falls_back_to_short_when_custom_is_none():
    """When the knob is unset and factor.mode is short (default), the resolver
    returns SHORT_TERM_FACTOR_EXPR. No-op for existing users."""
    _CACHE.clear()
    _CACHE["factor.mode"] = "short"
    _CACHE["factor.custom_expression"] = None
    assert _resolve_default_expr() == SHORT_TERM_FACTOR_EXPR


def test_resolver_returns_custom_when_set():
    """When the knob holds an expression string, it wins over factor.mode."""
    _CACHE.clear()
    _CACHE["factor.mode"] = "long"  # would normally win
    _CACHE["factor.custom_expression"] = "rank(returns)"
    assert _resolve_default_expr() == "rank(returns)"


def test_resolver_treats_empty_string_as_unset():
    """Defensive: an empty string is treated the same as None (defends against
    a UI that clears the field and submits ''). Falls through to preset."""
    _CACHE.clear()
    _CACHE["factor.mode"] = "long"
    _CACHE["factor.custom_expression"] = ""
    assert _resolve_default_expr() == LONG_TERM_FACTOR_EXPR
