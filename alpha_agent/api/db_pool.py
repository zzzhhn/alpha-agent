"""API-facing pool adapter: bound queue wait without changing cron pool semantics."""
from __future__ import annotations

import time
from contextlib import asynccontextmanager

from alpha_agent.api.performance import db_timing
from alpha_agent.storage.postgres import DBUnavailable


class APIConnectionPool:
    def __init__(self, pool, *, acquire_timeout: float = 10):
        self._pool = pool
        self.acquire_timeout = acquire_timeout

    def __getattr__(self, name):
        return getattr(self._pool, name)

    @asynccontextmanager
    async def acquire(self, *, timeout=None):
        start = time.monotonic()
        timing = db_timing.get()
        try:
            conn = await self._pool.acquire(
                timeout=self.acquire_timeout if timeout is None else timeout,
            )
        except TimeoutError as exc:
            raise DBUnavailable("Database connection queue timed out") from exc
        finally:
            if timing is not None:
                timing.wait_ms += (time.monotonic() - start) * 1000
        try:
            yield conn
        finally:
            # Pool.release shields its reset from request cancellation.
            await self._pool.release(conn)

    async def _call(self, method, *args, **kwargs):
        async with self.acquire() as conn:
            start = time.monotonic()
            timing = db_timing.get()
            try:
                return await getattr(conn, method)(*args, **kwargs)
            finally:
                if timing is not None:
                    timing.query_ms += (time.monotonic() - start) * 1000
                    timing.operations += 1

    async def fetch(self, *args, **kwargs):
        return await self._call("fetch", *args, **kwargs)

    async def fetchrow(self, *args, **kwargs):
        return await self._call("fetchrow", *args, **kwargs)

    async def fetchval(self, *args, **kwargs):
        return await self._call("fetchval", *args, **kwargs)

    async def execute(self, *args, **kwargs):
        return await self._call("execute", *args, **kwargs)

    async def executemany(self, *args, **kwargs):
        return await self._call("executemany", *args, **kwargs)
