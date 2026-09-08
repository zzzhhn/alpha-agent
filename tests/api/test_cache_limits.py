import asyncio

import pytest

from alpha_agent.api.cache import TTLCache


def test_lru_expiry_and_oversized_payload(monkeypatch):
    now = [100.0]
    monkeypatch.setattr("alpha_agent.api.cache.time.monotonic", lambda: now[0])
    cache = TTLCache(default_ttl=2, max_entries=2, max_bytes=2000)
    cache.set("a", {"value": 1})
    cache.set("b", {"value": 2})
    assert cache.get("a")
    cache.set("c", {"value": 3})
    assert cache.get("b") is None
    cache.set("huge", "x" * 3000)
    assert cache.get("huge") is None
    now[0] = 103
    cache.get("unrelated")
    assert not cache._store and cache._bytes == 0


@pytest.mark.asyncio
async def test_identical_readers_share_work_and_failures_are_retryable():
    cache = TTLCache()
    calls = 0

    async def load():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        return {"value": 1}

    results = await asyncio.gather(*(cache.get_or_load("public", load) for _ in range(5)))
    assert len(results) == 5 and calls == 1
    assert not cache._loading

    async def fail():
        raise ValueError("not cached")

    with pytest.raises(ValueError):
        await cache.get_or_load("retry", fail)
    assert await cache.get_or_load("retry", load) == {"value": 1}


@pytest.mark.asyncio
async def test_invalidation_during_load_prevents_old_cache_repopulation():
    cache = TTLCache()

    async def load():
        cache.invalidate("public")
        return {"old": True}

    await cache.get_or_load("public", load)
    assert cache.get("public") is None


@pytest.mark.asyncio
async def test_cancelled_owner_releases_slot_for_waiter():
    cache = TTLCache()
    started = asyncio.Event()

    async def slow():
        started.set()
        await asyncio.Event().wait()

    owner = asyncio.create_task(cache.get_or_load("a", slow))
    await started.wait()
    owner.cancel()
    with pytest.raises(asyncio.CancelledError):
        await owner

    async def replacement():
        return 42

    assert await cache.get_or_load("a", replacement) == 42
    assert not cache._loading
