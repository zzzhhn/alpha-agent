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
_UNCONFIGURED = object()  # distinguishes a missing row from a configured JSON null
_UNSET_HISTORY = "source='rollback' AND new_value IS NULL AND supersedes_change_id IS NOT NULL"


async def refresh_config(pool) -> None:
    """Load the live config and unconfiguration revisions in one snapshot."""
    known = dict(_CACHE_REVISIONS)
    rows = await pool.fetch(f"""
        SELECT key, value, updated_at, false AS unconfigured FROM engine_config
        UNION ALL
        SELECT field, NULL::jsonb, max(changed_at), true
        FROM config_change_log AS log
        WHERE {_UNSET_HISTORY}
          AND NOT EXISTS (SELECT 1 FROM engine_config WHERE key=log.field)
        GROUP BY field
    """)
    present = set()
    for row in rows:
        key = row["key"]
        present.add(key)
        raw = row["value"]
        value = _UNCONFIGURED if row["unconfigured"] else json.loads(raw) if isinstance(raw, str) else raw
        _publish(key, value, row["updated_at"])
    for key in set(_CACHE) - present:
        if _CACHE_REVISIONS.get(key) == known.get(key):
            _CACHE.pop(key, None)


def _publish(key, value, revision) -> None:
    if key in _CACHE_REVISIONS and revision < _CACHE_REVISIONS[key]:
        return
    if value is _UNCONFIGURED:
        _CACHE.pop(key, None)
    else:
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


async def _lock_config(conn, key):
    # Serialize writers even when the key does not have a row yet.
    await conn.execute("SELECT pg_advisory_xact_lock(hashtext('engine_config'), hashtext($1))", key)
    return await conn.fetchrow(
        "SELECT value::text AS value,updated_at,current_change_id FROM engine_config WHERE key=$1 FOR UPDATE",
        key,
    )


async def _write_locked_config(
    conn, writes, key, value, user_id, source, current, *, rollback_of=None, restored_change_id=None,
):
    previous_revision = current["updated_at"] if current else await conn.fetchval(
        f"SELECT max(changed_at) FROM config_change_log WHERE field=$1 AND {_UNSET_HISTORY}", key,
    )
    revision = await conn.fetchval(
        "SELECT GREATEST(clock_timestamp(),$1::timestamptz + interval '1 microsecond')",
        previous_revision,
    )
    encoded = None if value is _UNCONFIGURED else json.dumps(value)
    change_id = await conn.fetchval(
        "INSERT INTO config_change_log "
        "(user_id,field,old_value,new_value,source,changed_at,rollback_of,supersedes_change_id) "
        "VALUES ($1,$2,$3,$4,$5,$6,$7,$8) RETURNING id",
        user_id, key, current["value"] if current else None, encoded, source, revision,
        rollback_of, current["current_change_id"] if current else None,
    )
    if value is _UNCONFIGURED:
        await conn.execute("DELETE FROM engine_config WHERE key=$1", key)
    else:
        active_change_id = restored_change_id if rollback_of is not None else change_id
        await conn.execute(
            "INSERT INTO engine_config (key,value,updated_at,updated_by,current_change_id) "
            "VALUES ($1,$2::jsonb,$3,$4,$5) ON CONFLICT (key) DO UPDATE SET "
            "value=EXCLUDED.value,updated_at=EXCLUDED.updated_at,updated_by=EXCLUDED.updated_by,"
            "current_change_id=EXCLUDED.current_change_id",
            key, encoded, revision, user_id, active_change_id,
        )
    writes.append((key, value, revision))
    return change_id


async def write_config(conn, writes, key, value, user_id, source):
    current = await _lock_config(conn, key)
    return await _write_locked_config(conn, writes, key, value, user_id, source, current)


class ConfigRollbackConflict(ValueError):
    pass


async def rollback_config(
    conn, writes, key, user_id, *, applied_change_id, rollback_change_id, rollback_of=None,
):
    """Undo the active application, restoring its predecessor as the active version."""
    if rollback_change_id is not None:
        raise ConfigRollbackConflict("proposal already rolled back")
    if applied_change_id is None:
        raise ConfigRollbackConflict("approval lineage requires review")

    current = await _lock_config(conn, key)
    if current is not None and current["current_change_id"] is None:
        raise ConfigRollbackConflict("current config lineage requires review")
    if current is None or current["current_change_id"] != applied_change_id:
        raise ConfigRollbackConflict("approved version is no longer current")
    applied = await conn.fetchrow(
        "SELECT old_value,supersedes_change_id FROM config_change_log "
        "WHERE id=$1 AND field=$2 AND source='approved'",
        applied_change_id, key,
    )
    if applied is None:
        raise ConfigRollbackConflict("approval lineage requires review")
    old = applied["old_value"]
    value = _UNCONFIGURED if old is None else json.loads(old)
    change_id = await _write_locked_config(
        conn, writes, key, value, user_id, "rollback", current,
        rollback_of=rollback_of if rollback_of is not None else applied_change_id,
        restored_change_id=applied["supersedes_change_id"],
    )
    return change_id, DEFAULTS.get(key) if value is _UNCONFIGURED else value


async def set_config(pool, key: str, value: Any, user_id: int, source: str) -> None:
    async with config_transaction(pool) as (conn, writes):
        await write_config(conn, writes, key, value, user_id, source)
