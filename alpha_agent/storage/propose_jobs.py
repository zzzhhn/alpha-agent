"""CRUD helpers for the factor_propose_jobs table (Phase D async refactor).

Job lifecycle:
    queued  ─► running ─► done   (result_json populated)
                       ─► failed (error populated)

The POST /api/factor-lab/propose handler writes the initial 'queued' row
and spawns a FastAPI BackgroundTask; that task transitions to running,
runs the propose loop, then writes the terminal state. GET
/api/factor-lab/jobs/{id} reads the row for the frontend poll loop.
"""
from __future__ import annotations

import json
import math
import secrets
from typing import Any, Optional

import asyncpg


def _json_safe(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    return obj


def _gen_job_id() -> str:
    """Short, URL-safe, unguessable job id. 22 chars of base64url entropy
    (~128 bits). Not a UUID because the prefix `pj_` aids log-grepping."""
    return "pj_" + secrets.token_urlsafe(16)


async def create_job(pool: asyncpg.Pool, user_id: int, n: int) -> str:
    """Insert a new job row with status='queued'. Returns the new id."""
    job_id = _gen_job_id()
    await pool.execute(
        "INSERT INTO factor_propose_jobs (id, user_id, n, status) "
        "VALUES ($1, $2, $3, 'queued')",
        job_id, user_id, n,
    )
    return job_id


async def mark_running(pool: asyncpg.Pool, job_id: str) -> None:
    await pool.execute(
        "UPDATE factor_propose_jobs SET status='running', started_at=now() "
        "WHERE id=$1 AND status='queued'",
        job_id,
    )


async def mark_done(pool: asyncpg.Pool, job_id: str, result: dict) -> None:
    await pool.execute(
        "UPDATE factor_propose_jobs "
        "SET status='done', finished_at=now(), result_json=$2::jsonb "
        "WHERE id=$1",
        job_id, json.dumps(_json_safe(result)),
    )


async def mark_failed(pool: asyncpg.Pool, job_id: str, error: str) -> None:
    """Truncate error to 4KB so a runaway traceback can't bloat the row."""
    await pool.execute(
        "UPDATE factor_propose_jobs "
        "SET status='failed', finished_at=now(), error=$2 "
        "WHERE id=$1",
        job_id, error[:4096],
    )


async def get_job(pool: asyncpg.Pool, job_id: str) -> Optional[dict]:
    """Return job row as dict (status/result/error/timestamps) or None."""
    row = await pool.fetchrow(
        "SELECT id, user_id, status, n, "
        "       created_at, started_at, finished_at, "
        "       result_json, error "
        "FROM factor_propose_jobs WHERE id=$1",
        job_id,
    )
    if row is None:
        return None
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "status": row["status"],
        "n": row["n"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "started_at": row["started_at"].isoformat() if row["started_at"] else None,
        "finished_at": row["finished_at"].isoformat() if row["finished_at"] else None,
        "result": row["result_json"],
        "error": row["error"],
    }
