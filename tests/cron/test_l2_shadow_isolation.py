import json
from unittest.mock import AsyncMock

import pytest

from alpha_agent.storage.postgres import close_pool, get_pool


@pytest.fixture
async def pool(applied_db):
    value = await get_pool(applied_db)
    yield value
    await close_pool()


async def test_shadow_failure_isolated_after_live_books(pool, monkeypatch, applied_db):
    from api.cron import l2_cycle
    monkeypatch.setenv("DATABASE_URL", applied_db)
    monkeypatch.setattr(l2_cycle, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(l2_cycle.l2_driver, "ensure_strategy", AsyncMock(return_value=123))
    monkeypatch.setattr(l2_cycle.l2_driver, "run_driver", AsyncMock(return_value={"generated": 2}))
    ensure_live = AsyncMock(side_effect=[1001, 1002])
    monkeypatch.setattr(l2_cycle.l2_driver.l2_continuous, "ensure_book", ensure_live)
    calls = []

    async def drive(_pool, *, strategy_id, **kwargs):
        calls.append(strategy_id)
        if len(calls) == 3:
            raise ValueError("synthetic shadow failure")
        return {"generated": 0, "filled": 0}

    monkeypatch.setattr(l2_cycle.l2_driver, "run_continuous_driver", drive)
    out = await l2_cycle.handler()
    assert out["ok"] is True and out["generated"] == 2
    assert calls[:2] == [1001, 1002] and len(calls) == 5
    assert len(out["continuous"]) == 2
    assert "synthetic shadow failure" in out["shadow"]["shadow_factor_12_1"]["error"]
    assert out["shadow"]["shadow_band_40_80"]["generated"] == 0
    detail = json.loads(await pool.fetchval("SELECT details FROM cron_runs WHERE cron_name='l2_cycle'"))
    assert detail["shadow"] == out["shadow"]
    # The same lock has been released despite the shadow exception.
    async with pool.acquire() as conn:
        assert await conn.fetchval("SELECT pg_try_advisory_lock(hashtext('l2_cycle_continuous_v2'))")
        await conn.execute("SELECT pg_advisory_unlock(hashtext('l2_cycle_continuous_v2'))")
