import asyncio
from unittest.mock import AsyncMock

import pytest

from alpha_agent.storage.postgres import close_pool, get_pool
from api.cron import fast_intraday


async def test_overlap_then_cancel_releases_shard_lease(applied_db, monkeypatch):
    pool = await get_pool(applied_db)
    monkeypatch.setenv("DATABASE_URL", applied_db)
    monkeypatch.setattr(fast_intraday, "get_pool", AsyncMock(return_value=pool))
    entered = asyncio.Event()

    async def busy(**kwargs):
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(fast_intraday, "_run_handler", busy)
    first = asyncio.create_task(fast_intraday.handler(offset=40, run_key="same-slot"))
    try:
        await asyncio.wait_for(entered.wait(), 3)
        duplicate = await fast_intraday.handler(offset=40, run_key="same-slot")
        assert duplicate["reason"] == "duplicate_or_overlapping_shard"
    finally:
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        await close_pool()
    # A different client can immediately take that exact lock after cancellation.
    pool = await get_pool(applied_db)
    monkeypatch.setattr(fast_intraday, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(fast_intraday, "_run_handler", AsyncMock(return_value={"ran": True}))
    try:
        assert await fast_intraday.handler(offset=40, run_key="same-slot") == {"ran": True}
    finally:
        await close_pool()
