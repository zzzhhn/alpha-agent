# tests/signals/test_factor_mode_config.py
"""Phase 2-pre: factor mode reads from config_store at call time.

These tests manipulate _CACHE directly (no DB) to verify that
_resolve_default_expr() honours the runtime config override over the
env var, and falls back to the env/short default when cache is cold.
"""
from __future__ import annotations

import pytest

from alpha_agent import config_store
from alpha_agent.signals.factor import (
    LONG_TERM_FACTOR_EXPR,
    SHORT_TERM_FACTOR_EXPR,
    _resolve_default_expr,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    """Ensure a cold cache before and after every test in this module."""
    config_store._CACHE.clear()
    yield
    config_store._CACHE.clear()


# ---------------------------------------------------------------------------
# Default / cold-cache behaviour
# ---------------------------------------------------------------------------


def test_factor_mode_default_short_cold_cache(monkeypatch):
    """Cold cache + no env var → SHORT_TERM_FACTOR_EXPR (platform default)."""
    monkeypatch.delenv("ALPHA_FACTOR_MODE", raising=False)
    assert _resolve_default_expr() == SHORT_TERM_FACTOR_EXPR


def test_factor_mode_default_short_env_short(monkeypatch):
    """Cold cache + ALPHA_FACTOR_MODE=short → SHORT_TERM_FACTOR_EXPR."""
    monkeypatch.setenv("ALPHA_FACTOR_MODE", "short")
    assert _resolve_default_expr() == SHORT_TERM_FACTOR_EXPR


def test_factor_mode_env_long_cold_cache(monkeypatch):
    """Cold cache + ALPHA_FACTOR_MODE=long → LONG_TERM_FACTOR_EXPR
    (env var still works as a fallback when cache is cold)."""
    monkeypatch.setenv("ALPHA_FACTOR_MODE", "long")
    assert _resolve_default_expr() == LONG_TERM_FACTOR_EXPR


# ---------------------------------------------------------------------------
# Config store override — the new behaviour under test
# ---------------------------------------------------------------------------


def test_factor_mode_config_long_overrides_env_short(monkeypatch):
    """config_store key 'factor.mode'='long' wins over env var 'short'."""
    monkeypatch.setenv("ALPHA_FACTOR_MODE", "short")
    config_store._CACHE["factor.mode"] = "long"
    assert _resolve_default_expr() == LONG_TERM_FACTOR_EXPR


def test_factor_mode_config_short_overrides_env_long(monkeypatch):
    """config_store key 'factor.mode'='short' wins over env var 'long'."""
    monkeypatch.setenv("ALPHA_FACTOR_MODE", "long")
    config_store._CACHE["factor.mode"] = "short"
    assert _resolve_default_expr() == SHORT_TERM_FACTOR_EXPR


def test_factor_mode_config_unknown_falls_back_to_short():
    """Unrecognised config value (neither 'long' nor 'short') → SHORT."""
    config_store._CACHE["factor.mode"] = "weekly"  # unknown — should default to short
    assert _resolve_default_expr() == SHORT_TERM_FACTOR_EXPR


def test_factor_mode_config_long_no_env(monkeypatch):
    """Config 'long' works even when ALPHA_FACTOR_MODE is unset."""
    monkeypatch.delenv("ALPHA_FACTOR_MODE", raising=False)
    config_store._CACHE["factor.mode"] = "long"
    assert _resolve_default_expr() == LONG_TERM_FACTOR_EXPR


def test_factor_mode_read_at_call_time_not_frozen():
    """Verify mode is resolved on every call so a cache update takes effect
    without restarting the process (guards against import-frozen reads)."""
    config_store._CACHE["factor.mode"] = "short"
    first = _resolve_default_expr()

    config_store._CACHE["factor.mode"] = "long"
    second = _resolve_default_expr()

    assert first == SHORT_TERM_FACTOR_EXPR
    assert second == LONG_TERM_FACTOR_EXPR
    assert first != second  # the flip must happen without reimport
