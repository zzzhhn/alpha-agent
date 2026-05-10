"""FastAPI dependency helpers for M2 API routes.

get_db_pool() is a thin async wrapper around the module-level singleton
in alpha_agent.storage.postgres.  All M2 route handlers call this to
obtain the pool; it is the single injection point for the DATABASE_URL
env var so tests can monkeypatch it before creating the TestClient.
"""
from __future__ import annotations

import os

import asyncpg

from alpha_agent.storage.postgres import get_pool


async def get_db_pool() -> asyncpg.Pool:
    """Return the module-level singleton pool, creating it on first call.

    Reads DATABASE_URL from the environment at call time so test fixtures
    can monkeypatch.setenv("DATABASE_URL", applied_db) before the first
    request is dispatched.
    """
    dsn = os.environ["DATABASE_URL"]
    return await get_pool(dsn)
