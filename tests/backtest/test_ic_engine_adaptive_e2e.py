# tests/backtest/test_ic_engine_adaptive_e2e.py
import json
from datetime import UTC, datetime, timedelta

import pytest

from alpha_agent.backtest.ic_engine import run_monthly_ic_backtest
from alpha_agent.fusion.combine import load_weights
from alpha_agent.storage.postgres import close_pool, get_pool


@pytest.fixture
async def pool(applied_db):
    p = await get_pool(applied_db)
    yield p
    await close_pool()


async def _seed_pair(pool, ticker, as_of, signal_val, ret_5d, signal_name="news"):
    await pool.execute(
        "INSERT INTO daily_signals_fast (ticker,date,composite,rating,confidence,breakdown,partial,fetched_at) "
        "VALUES ($1,$2::date,$3,'HOLD',0.7,$4::jsonb,false,$5) "
        "ON CONFLICT (ticker,date) DO UPDATE SET breakdown=EXCLUDED.breakdown",
        ticker, as_of.date(), float(signal_val),
        json.dumps({"breakdown": [{"signal": signal_name, "z": float(signal_val)}]}), as_of,
    )
    entry, exit_ = 100.0, 100.0 * (1 + ret_5d)
    for off, c in enumerate([entry, entry, entry, entry, entry, exit_]):
        await pool.execute(
            "INSERT INTO daily_prices (ticker,date,close) VALUES ($1,$2::date,$3) "
            "ON CONFLICT (ticker,date) DO UPDATE SET close=EXCLUDED.close",
            ticker, (as_of + timedelta(days=off)).date(), c,
        )


@pytest.mark.asyncio
async def test_run_backtest_produces_live_weights_via_adaptive(pool):
    now = datetime.now(UTC).replace(hour=20, minute=0, second=0, microsecond=0)
    for i in range(15):
        await _seed_pair(pool, f"T{i:02d}", now - timedelta(days=20 - i + 5),
                         signal_val=i * 0.1, ret_5d=i * 0.005)
    await run_monthly_ic_backtest(pool)
    assert await pool.fetchval("SELECT count(*) FROM signal_ic_history WHERE signal_name='news'") > 0
    weights = await load_weights(pool)
    assert "news" in weights
    live_count = await pool.fetchval(
        "SELECT count(*) FROM signal_weight_current WHERE signal_name='news' AND status='live'")
    assert live_count == 1
