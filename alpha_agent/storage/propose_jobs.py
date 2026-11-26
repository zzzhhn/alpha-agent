"""Durable proposal queue. A committed claim is executed at most once."""
from __future__ import annotations

import json
import math
import secrets
from datetime import datetime, timedelta
from typing import Any

import asyncpg

# A worker invocation budgets 270s of the platform's 300s limit. A claim
# surviving 300s cannot safely be resumed because its paid work is unknown.
CLAIM_TTL = timedelta(minutes=5)
WORKER_INTERRUPTED = "worker_interrupted"
_ACTIVE_CLAIM = (
    "id=$1 AND started_at=$2 AND status='running' "
    "AND started_at > clock_timestamp() - $3::interval"
)


def _json_safe(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    return obj


def _gen_job_id() -> str:
    return "pj_" + secrets.token_urlsafe(16)


async def create_job(pool: asyncpg.Pool, user_id: int, n: int) -> str:
    job_id = _gen_job_id()
    await pool.execute(
        "INSERT INTO factor_propose_jobs (id, user_id, n, status) VALUES ($1, $2, $3, 'queued')",
        job_id, user_id, n,
    )
    return job_id


async def create_completed_job(pool: asyncpg.Pool, user_id: int, n: int, result: dict) -> str:
    """Record an inline dormant result without publishing a claimable row."""
    job_id = _gen_job_id()
    await pool.execute(
        "INSERT INTO factor_propose_jobs (id, user_id, n, status, finished_at, result_json) "
        "VALUES ($1, $2, $3, 'done', clock_timestamp(), $4::jsonb)",
        job_id, user_id, n, json.dumps(_json_safe(result)),
    )
    return job_id


async def claim_oldest_queued(pool: asyncpg.Pool) -> dict | None:
    """Claim one queued row atomically and return its database-issued fence."""
    row = await pool.fetchrow(
        "UPDATE factor_propose_jobs SET status='running', started_at=clock_timestamp(), "
        """result_json='{"_job_progress":{"stage":"preparing"}}'::jsonb """
        "WHERE id = ("
        "  SELECT id FROM factor_propose_jobs WHERE status='queued' "
        "  ORDER BY created_at ASC, id ASC LIMIT 1 FOR UPDATE SKIP LOCKED"
        ") "
        "RETURNING id, user_id, n, started_at"
    )
    return dict(row) if row is not None else None


async def expire_interrupted(
    pool: asyncpg.Pool, *, job_id: str | None = None, user_id: int | None = None,
) -> int:
    """Expire abandoned claims once and preserve their last committed progress."""
    result = await pool.execute(
        "UPDATE factor_propose_jobs "
        "SET status='failed', finished_at=clock_timestamp(), error=$1 "
        "WHERE status='running' "
        "AND COALESCE(started_at, created_at) <= clock_timestamp() - $2::interval "
        "AND ($3::text IS NULL OR id=$3) "
        "AND ($4::bigint IS NULL OR user_id=$4)",
        WORKER_INTERRUPTED, CLAIM_TTL, job_id, user_id,
    )
    return int(result.rsplit(" ", 1)[1])


async def save_progress(
    pool: asyncpg.Pool, job_id: str, started_at: datetime, progress: dict,
) -> bool:
    updated = await pool.fetchval(
        "UPDATE factor_propose_jobs "
        "SET result_json=COALESCE(result_json, '{}'::jsonb) || jsonb_build_object('_job_progress', $4::jsonb) "
        f"WHERE {_ACTIVE_CLAIM} RETURNING true",
        job_id, started_at, CLAIM_TTL, json.dumps(_json_safe(progress)),
    )
    return bool(updated)


async def mark_done(pool: asyncpg.Pool, job_id: str, started_at: datetime, result: dict) -> bool:
    updated = await pool.fetchval(
        "UPDATE factor_propose_jobs "
        "SET status='done', finished_at=clock_timestamp(), result_json=$4::jsonb, error=NULL "
        f"WHERE {_ACTIVE_CLAIM} RETURNING true",
        job_id, started_at, CLAIM_TTL, json.dumps(_json_safe(result)),
    )
    return bool(updated)


async def mark_failed(
    pool: asyncpg.Pool, job_id: str, started_at: datetime, error: str, *, result: dict | None = None,
) -> bool:
    updated = await pool.fetchval(
        "UPDATE factor_propose_jobs "
        "SET status='failed', finished_at=clock_timestamp(), error=$4, "
        "result_json=CASE WHEN $5::jsonb IS NULL THEN result_json "
        "ELSE COALESCE(result_json, '{}'::jsonb) || $5::jsonb END "
        f"WHERE {_ACTIVE_CLAIM} RETURNING true",
        job_id, started_at, CLAIM_TTL, error[:4096],
        json.dumps(_json_safe(result)) if result is not None else None,
    )
    return bool(updated)


async def get_job(pool: asyncpg.Pool, job_id: str) -> dict | None:
    """Decode the stored checkpoint separately from an accepted result."""
    row = await pool.fetchrow(
        "SELECT id, user_id, status, n, created_at, started_at, finished_at, result_json, error "
        "FROM factor_propose_jobs WHERE id=$1",
        job_id,
    )
    if row is None:
        return None

    job = dict(row)
    for key in ("created_at", "started_at", "finished_at"):
        if job[key] is not None:
            job[key] = job[key].isoformat()
    result = job.pop("result_json")
    if isinstance(result, str):
        result = json.loads(result)
    job["progress"] = result.pop("_job_progress", None) if isinstance(result, dict) else None
    job["result"] = result or None
    job["error_code"] = (
        WORKER_INTERRUPTED if job["status"] == "failed" and job["error"] == WORKER_INTERRUPTED else None
    )
    return job
