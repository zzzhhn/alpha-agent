"""Runtime engine-config store (Phase 2-pre).

Knobs are read in hot, pure, synchronous functions (e.g. rating.map_to_tier),
so a per-call DB read is not viable. Instead a process-level cache is loaded
by refresh_config(pool) (called at the top of cron handlers / request entry),
and get_config(key, default) reads it synchronously. A cold cache or unset key
falls back to the caller-supplied default (the historic hardcoded value).

Writes go through set_config, which upserts engine_config AND journals the
change to config_change_log (the shared Phase 1b/2b rollback substrate).
"""
from __future__ import annotations

import json
from typing import Any

DEFAULTS: dict[str, Any] = {
    "rating.tier_thresholds": {"buy": 1.5, "ow": 0.5, "hold": -0.5, "uw": -1.5},
    "rating.no_trade_band": 0.15,
    "factor.mode": "short",
    "signal.ic_accept_threshold": 0.02,
    # Phase 3a: free-form factor expression. None = fall back to factor.mode
    # short/long preset (full backward compat). Set via Phase 3d Approve.
    "factor.custom_expression": None,
}

_CACHE: dict[str, Any] = {}
_SENTINEL = object()  # distinguishes "no default passed" from a falsy default (0/False/[])


async def refresh_config(pool) -> None:
    """Load every engine_config row into the process cache. Call at the top of
    cron handlers and request-path entry so reads see the latest values."""
    rows = await pool.fetch("SELECT key, value FROM engine_config")
    fresh: dict[str, Any] = {}
    for r in rows:
        v = r["value"]
        fresh[r["key"]] = json.loads(v) if isinstance(v, str) else v
    _CACHE.clear()
    _CACHE.update(fresh)


def get_config(key: str, default: Any = _SENTINEL) -> Any:
    """Synchronous cache read. Falls back to the cached value, else the
    caller's default (the historic hardcoded value), else the DEFAULTS table.
    A sentinel default lets a caller pass a legitimately falsy default
    (0 / False / []) without it being treated as 'no default'."""
    if key in _CACHE:
        return _CACHE[key]
    if default is not _SENTINEL:
        return default
    return DEFAULTS.get(key)


async def set_config(pool, key: str, value: Any, user_id: int, source: str) -> None:
    """Upsert the live value + journal the change to config_change_log, then
    update the cache so the new value is visible in-process immediately."""
    old = await pool.fetchval("SELECT value FROM engine_config WHERE key = $1", key)
    await pool.execute(
        "INSERT INTO engine_config (key, value, updated_at, updated_by) "
        "VALUES ($1, $2::jsonb, now(), $3) "
        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, "
        "updated_at = EXCLUDED.updated_at, updated_by = EXCLUDED.updated_by",
        key, json.dumps(value), user_id,
    )
    old_text = old if isinstance(old, str) else (json.dumps(old) if old is not None else None)
    await pool.execute(
        "INSERT INTO config_change_log (user_id, field, old_value, new_value, source) "
        "VALUES ($1, $2, $3, $4, $5)",
        user_id, key, old_text, json.dumps(value), source,
    )
    _CACHE[key] = value
