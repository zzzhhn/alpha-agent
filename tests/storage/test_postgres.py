import pytest

import asyncpg

from alpha_agent.storage.postgres import (
    DBUnavailable,
    get_pool,
    close_pool,
    with_retry,
)

pytestmark = pytest.mark.asyncio


async def test_get_pool_returns_singleton(applied_db):
    p1 = await get_pool(applied_db)
    p2 = await get_pool(applied_db)
    assert p1 is p2
    await close_pool()


async def test_with_retry_passes_through_on_success():
    calls = 0
    @with_retry
    async def op():
        nonlocal calls
        calls += 1
        return 42
    assert await op() == 42
    assert calls == 1


async def test_with_retry_succeeds_after_transient_failure():
    calls = 0
    @with_retry
    async def op():
        nonlocal calls
        calls += 1
        if calls < 3:
            raise asyncpg.PostgresConnectionError("simulated wake")
        return "ok"
    assert await op() == "ok"
    assert calls == 3


async def test_with_retry_raises_dbunavailable_after_exhaustion():
    @with_retry
    async def op():
        raise asyncpg.PostgresConnectionError("permanent")
    with pytest.raises(DBUnavailable):
        await op()


async def test_with_retry_reraises_other_errors_immediately():
    calls = 0
    @with_retry
    async def op():
        nonlocal calls
        calls += 1
        raise ValueError("not retryable")
    with pytest.raises(ValueError):
        await op()
    assert calls == 1
