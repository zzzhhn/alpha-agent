"""Typed CRUD helpers backed by raw SQL. Imported by cron/API code only;
direct asyncpg usage outside this module is a code smell.
"""
from __future__ import annotations

import json
import math
from typing import Any

import asyncpg


def _json_safe(obj: Any) -> Any:
    """Walk a dict/list/scalar, replacing NaN/+Inf/-Inf with None.

    Postgres JSONB rejects NaN/Inf (per JSON spec) but Python json.dumps
    happily emits them as literal `NaN`/`Infinity` tokens. Sanitize at the
    storage boundary so callers don't have to remember to filter NaNs out
    of every signal breakdown."""
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    return obj


def _dumps(obj: Any) -> str:
    return json.dumps(_json_safe(obj))


async def insert_signal_slow(
    pool: asyncpg.Pool,
    ticker: str,
    date: str,
    composite_partial: float,
    breakdown: dict[str, Any],
) -> None:
    await pool.execute(
        """
        INSERT INTO daily_signals_slow
            (ticker, date, composite_partial, breakdown, fetched_at)
        VALUES ($1, $2::text::date, $3, $4::jsonb, now())
        ON CONFLICT (ticker, date) DO UPDATE SET
            composite_partial = EXCLUDED.composite_partial,
            breakdown = EXCLUDED.breakdown,
            fetched_at = EXCLUDED.fetched_at
        """,
        ticker, date, composite_partial, _dumps(breakdown),
    )


async def upsert_signal_fast(
    pool: asyncpg.Pool,
    ticker: str,
    date: str,
    composite: float,
    rating: str,
    confidence: float,
    breakdown: dict[str, Any],
    partial: bool = False,
) -> None:
    await pool.execute(
        """
        INSERT INTO daily_signals_fast
            (ticker, date, composite, rating, confidence, breakdown, partial, fetched_at)
        VALUES ($1, $2::text::date, $3, $4, $5, $6::jsonb, $7, now())
        ON CONFLICT (ticker, date) DO UPDATE SET
            composite = EXCLUDED.composite,
            rating = EXCLUDED.rating,
            confidence = EXCLUDED.confidence,
            breakdown = EXCLUDED.breakdown,
            partial = EXCLUDED.partial,
            fetched_at = EXCLUDED.fetched_at
        """,
        ticker, date, composite, rating, confidence, _dumps(breakdown), partial,
    )


async def enqueue_alert(
    pool: asyncpg.Pool,
    ticker: str,
    type_: str,
    payload: dict[str, Any],
    dedup_bucket: int,
) -> None:
    """Idempotent within (ticker, type, dedup_bucket). Caller computes bucket
    as floor(epoch / 1800) for 30-min windows."""
    await pool.execute(
        """
        INSERT INTO alert_queue (ticker, type, payload, dedup_bucket)
        VALUES ($1, $2, $3::jsonb, $4)
        ON CONFLICT (ticker, type, dedup_bucket) DO NOTHING
        """,
        ticker, type_, _dumps(payload), dedup_bucket,
    )


async def list_pending_alerts(pool: asyncpg.Pool, limit: int) -> list[asyncpg.Record]:
    return await pool.fetch(
        """
        SELECT id, ticker, type, payload, created_at
        FROM alert_queue
        WHERE dispatched = false
        ORDER BY created_at ASC
        LIMIT $1
        """,
        limit,
    )


async def mark_alert_dispatched(pool: asyncpg.Pool, alert_id: int) -> None:
    await pool.execute("UPDATE alert_queue SET dispatched = true WHERE id = $1", alert_id)


async def log_error(
    pool: asyncpg.Pool,
    *,
    layer: str,
    component: str,
    ticker: str | None = None,
    err_type: str | None = None,
    err_message: str | None = None,
    context: dict[str, Any] | None = None,
) -> None:
    await pool.execute(
        """
        INSERT INTO error_log (layer, component, ticker, err_type, err_message, context)
        VALUES ($1, $2, $3, $4, $5, $6::jsonb)
        """,
        layer, component, ticker, err_type, err_message, _dumps(context or {}),
    )
