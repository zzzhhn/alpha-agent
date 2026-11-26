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
from contextlib import asynccontextmanager
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
_CACHE_REVISIONS = {}
_SENTINEL = object()  # distinguishes "no default passed" from a falsy default (0/False/[])


async def refresh_config(pool) -> None:
    """Load every engine_config row into the process cache. Call at the top of
    cron handlers and request-path entry so reads see the latest values."""
    known = dict(_CACHE_REVISIONS)
    rows = await pool.fetch("SELECT key, value, updated_at FROM engine_config")
    present = set()
    for row in rows:
        key = row["key"]
        present.add(key)
        value = row["value"]
        _publish(key, json.loads(value) if isinstance(value, str) else value, row["updated_at"])
    for key in set(_CACHE) - present:
        if _CACHE_REVISIONS.get(key) == known.get(key):
            _CACHE.pop(key, None)
            _CACHE_REVISIONS.pop(key, None)


def _publish(key, value, revision) -> None:
    if key not in _CACHE or key not in _CACHE_REVISIONS or revision >= _CACHE_REVISIONS[key]:
        _CACHE[key] = value
        _CACHE_REVISIONS[key] = revision


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


@asynccontextmanager
async def config_transaction(pool):
    """Commit the decision and journal together before publishing to this process."""
    writes = []
    async with pool.acquire() as conn:
        async with conn.transaction():
            yield conn, writes
        for key, value, revision in writes:
            _publish(key, value, revision)


async def write_config(conn, writes, key, value, user_id, source):
    # Also serializes the first write, before a row exists to lock.
    await conn.execute("SELECT pg_advisory_xact_lock(hashtext('engine_config'), hashtext($1))", key)
    old = await conn.fetchval("SELECT value FROM engine_config WHERE key=$1 FOR UPDATE", key)
    encoded = json.dumps(value)
    revision = await conn.fetchval(
        "INSERT INTO engine_config (key, value, updated_at, updated_by) "
        "VALUES ($1,$2::jsonb,clock_timestamp(),$3) ON CONFLICT (key) DO UPDATE SET "
        "value=EXCLUDED.value, updated_by=EXCLUDED.updated_by, "
        "updated_at=GREATEST(clock_timestamp(),engine_config.updated_at + interval '1 microsecond') "
        "RETURNING updated_at", key, encoded, user_id,
    )
    old_text = old if isinstance(old, str) or old is None else json.dumps(old)
    change_id = await conn.fetchval(
        "INSERT INTO config_change_log (user_id,field,old_value,new_value,source,changed_at) "
        "VALUES ($1,$2,$3,$4,$5,$6) RETURNING id",
        user_id, key, old_text, encoded, source, revision,
    )
    writes.append((key, value, revision))
    return change_id


async def set_config(pool, key: str, value: Any, user_id: int, source: str) -> None:
    async with config_transaction(pool) as (conn, writes):
        await write_config(conn, writes, key, value, user_id, source)
