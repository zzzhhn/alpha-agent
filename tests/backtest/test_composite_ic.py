# tests/backtest/test_composite_ic.py
import json
from datetime import date, timedelta

import pytest

from alpha_agent.backtest.adaptive_weights import composite_ic
from alpha_agent.storage.postgres import close_pool, get_pool


@pytest.fixture
async def pool(applied_db):
    p = await get_pool(applied_db)
    yield p
    await close_pool()


async def _seed(pool, ticker, as_of, z_a, z_b, fwd_pct):
    await pool.execute(
        "INSERT INTO daily_signals_fast (ticker, date, composite, breakdown, fetched_at) "
        "VALUES ($1,$2::date,0.0,$3::jsonb,now()) "
        "ON CONFLICT (ticker,date) DO UPDATE SET breakdown=EXCLUDED.breakdown",
        ticker, as_of,
        json.dumps({"breakdown": [
            {"signal": "siga", "z": z_a},
            {"signal": "sigb", "z": z_b},
        ]}),
    )
    closes = [100, 100, 100, 100, 100, 100 * (1 + fwd_pct)]
    for i, c in enumerate(closes):
        await pool.execute(
            "INSERT INTO daily_prices (ticker, date, close) VALUES ($1,$2::date,$3) "
            "ON CONFLICT (ticker,date) DO UPDATE SET close=EXCLUDED.close",
            ticker, as_of + timedelta(days=i), c,
        )


@pytest.mark.asyncio
async def test_composite_ic_rewards_the_return_driving_signal(pool):
    # siga z drives the forward return monotonically; sigb is noise (zero z).
    base = date.today() - timedelta(days=40)
    for k in range(12):
        za = (k - 5.5) / 6.0
        await _seed(pool, f"T{k:02d}", base, z_a=za, z_b=0.0, fwd_pct=za * 0.1)
    ic_a = await composite_ic(pool, {"siga": 1.0, "sigb": 0.0}, window_days=90)
    ic_b = await composite_ic(pool, {"siga": 0.0, "sigb": 1.0}, window_days=90)
    assert ic_a is not None and ic_a > 0.9      # tracks the driver -> high IC
    assert ic_b is None or abs(ic_b) < 0.3      # pure noise -> ~0 / undefined


@pytest.mark.asyncio
async def test_composite_ic_none_below_min_obs(pool):
    base = date.today() - timedelta(days=40)
    await _seed(pool, "ONLY", base, z_a=0.5, z_b=0.0, fwd_pct=0.05)
    assert await composite_ic(pool, {"siga": 1.0}, window_days=90) is None
