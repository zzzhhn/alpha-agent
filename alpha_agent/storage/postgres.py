"""Async Postgres connection pool with retry-aware decorator.

Spec §5.3: Neon free tier auto-suspends after idle. Wake adds 200-500ms.
Three-attempt exponential backoff handles wake; non-connection errors
(programming bugs, constraint violations) propagate immediately.

Pool state is module-level singleton — intentional. All callers share one
pool per process. Call close_pool() in teardown / lifespan shutdown hooks.
"""
from __future__ import annotations

import asyncio
import functools
import logging
import os
from typing import Any, Awaitable, Callable, TypeVar

import asyncpg

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None
_pool_dsn: str | None = None
_pool_lock: asyncio.Lock | None = None

T = TypeVar("T")


class DBUnavailable(Exception):
    """Raised when retries exhausted; API layer maps this to 503 DB_UNAVAILABLE."""


async def get_pool(dsn: str, *, min_size: int = 1, max_size: int | None = None) -> asyncpg.Pool:
    """One bounded pool per process, including concurrent cold-start requests."""
    global _pool, _pool_dsn, _pool_lock
    if _pool_lock is None:
        _pool_lock = asyncio.Lock()
    async with _pool_lock:
        if _pool is not None:
            if _pool_dsn != dsn:
                # A DSN includes the database password. Never render it in errors.
                raise RuntimeError("Pool already exists for a different database")
            return _pool
        size = max_size if max_size is not None else int(os.getenv("DB_POOL_MAX_SIZE", "5"))
        _pool = await asyncpg.create_pool(
            dsn, min_size=min_size, max_size=size, timeout=15,
            command_timeout=60, max_inactive_connection_lifetime=120,
        )
        _pool_dsn = dsn
        return _pool


async def close_pool() -> None:
    """Close and discard the singleton pool. Safe to call when no pool exists."""
    global _pool, _pool_dsn, _pool_lock
    if _pool is not None:
        await _pool.close()
        _pool = None
        _pool_dsn = None
    _pool_lock = None


# Exception types that indicate a transient connection-level failure.
_RETRYABLE = (
    asyncpg.PostgresConnectionError,
    asyncpg.exceptions.ConnectionDoesNotExistError,
    asyncio.TimeoutError,
)

# Three retries: attempts 1-4 with delays 0s, 0.5s, 1.0s, 2.0s before each.
_ATTEMPT_DELAYS = [0.0, 0.5, 1.0, 2.0]


def with_retry(fn: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
    """Decorator: up to 4 attempts with exponential backoff (0.5s, 1s, 2s).

    Only asyncpg connection-level errors and asyncio.TimeoutError trigger a
    retry. All other exceptions propagate immediately so programming errors
    and constraint violations surface without delay.
    """

    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> T:
        last_exc: Exception | None = None
        for attempt, delay in enumerate(_ATTEMPT_DELAYS):
            if delay > 0:
                await asyncio.sleep(delay)
            try:
                return await fn(*args, **kwargs)
            except _RETRYABLE as exc:
                last_exc = exc
                logger.warning(
                    "DB op %s failed (attempt %d/%d): %s",
                    fn.__name__,
                    attempt + 1,
                    len(_ATTEMPT_DELAYS),
                    exc,
                )
        raise DBUnavailable(
            f"{fn.__name__} failed after {len(_ATTEMPT_DELAYS)} attempts"
        ) from last_exc

    return wrapper
