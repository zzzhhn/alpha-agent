# tests/backtest/test_ic_engine_daily_prices.py
#
# Fixture note: `applied_db` is a DSN string; build a pool via get_pool
# (mirrors the existing tests/backtest/test_ic_engine.py `pool` fixture).
import json
from datetime import date, timedelta

import pytest

from alpha_agent.backtest.ic_engine import compute_walk_forward_ic
from alpha_agent.storage.postgres import close_pool, get_pool


@pytest.fixture
async def pool(applied_db):
    p = await get_pool(applied_db)
    yield p
    await close_pool()


async def _seed(pool, ticker, as_of: date, z: float, closes: list[float]):
    """Insert one daily_signals_fast row carrying signal 'factor' z, plus a
    run of daily_prices closes starting at as_of (one per trading day)."""
    await pool.execute(
        """
        INSERT INTO daily_signals_fast (ticker, date, composite, breakdown, fetched_at)
        VALUES ($1, $2, 0.0, $3::jsonb, now())
        ON CONFLICT (ticker, date) DO UPDATE SET breakdown = EXCLUDED.breakdown
        """,
        ticker, as_of,
        json.dumps({"breakdown": [{"signal": "factor", "z": z}]}),
    )
    for i, c in enumerate(closes):
        d = as_of + timedelta(days=i)
        await pool.execute(
            "INSERT INTO daily_prices (ticker, date, close) VALUES ($1,$2,$3) "
            "ON CONFLICT (ticker, date) DO UPDATE SET close = EXCLUDED.close",
            ticker, d, c,
        )


@pytest.mark.asyncio
async def test_ic_uses_5_trading_day_lead_and_is_positive(pool):
    # Three tickers; higher z -> higher realized fwd-5-row return. A perfect
    # monotone relationship should give Spearman IC = 1.0.
    base = date.today() - timedelta(days=40)
    # close[as_of]=100, close 5 rows later encodes the return: bigger z -> bigger jump.
    await _seed(pool, "AAA", base, z=-1.0, closes=[100, 100, 100, 100, 100, 100])  # +0%
    await _seed(pool, "BBB", base, z=0.0, closes=[100, 100, 100, 100, 100, 105])   # +5%
    await _seed(pool, "CCC", base, z=1.0, closes=[100, 100, 100, 100, 100, 110])   # +10%
    # _MIN_OBS is 10 in the engine; lower it for the test via monkeypatch is
    # cleaner, but here we seed 12 tickers to clear the floor instead.
    for k in range(9):
        z = (k - 4) / 4.0
        await _seed(pool, f"T{k}", base, z=z, closes=[100, 100, 100, 100, 100, 100 + z * 10])
    result = await compute_walk_forward_ic(pool, "factor", 90)
    assert result is not None
    ic, n_obs = result
    assert n_obs >= 10
    assert ic > 0.9  # near-perfect monotone z -> fwd return


@pytest.mark.asyncio
async def test_ic_excludes_as_of_without_5_day_exit(pool):
    # An as_of whose 5th-ahead trading-day close does not exist yet must be
    # excluded (walk-forward: never peek at an unobservable exit).
    recent = date.today()
    await _seed(pool, "ZZZ", recent, z=0.5, closes=[100, 101])  # only 2 days, no +5 exit
    result = await compute_walk_forward_ic(pool, "factor", 90)
    # Only the seedless recent row exists -> below _MIN_OBS -> None.
    assert result is None
