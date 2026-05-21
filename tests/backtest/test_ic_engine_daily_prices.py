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
    # 12 tickers with STRICTLY monotone z -> fwd-5-row return (no ties in
    # either axis), so the Spearman rank IC is deterministically 1.0 regardless
    # of the DB row-return order. _MIN_OBS is 10 in the engine, so 12 clears it.
    # close[as_of]=100; the 6th close (LEAD 5 rows ahead) encodes the return.
    base = date.today() - timedelta(days=40)
    for k in range(12):
        z = (k - 5.5) / 6.0  # 12 distinct values, strictly increasing
        pct = z * 0.1        # strictly increasing forward return, no ties
        exit_close = 100.0 * (1.0 + pct)
        await _seed(
            pool, f"T{k:02d}", base, z=z,
            closes=[100, 100, 100, 100, 100, exit_close],
        )
    result = await compute_walk_forward_ic(pool, "factor", 90)
    assert result is not None
    ic, n_obs = result
    assert n_obs >= 10
    assert ic > 0.99  # strictly monotone z -> fwd return gives Spearman = 1.0


@pytest.mark.asyncio
async def test_ic_excludes_as_of_without_5_day_exit(pool):
    # An as_of whose 5th-ahead trading-day close does not exist yet must be
    # excluded (walk-forward: never peek at an unobservable exit).
    recent = date.today()
    await _seed(pool, "ZZZ", recent, z=0.5, closes=[100, 101])  # only 2 days, no +5 exit
    result = await compute_walk_forward_ic(pool, "factor", 90)
    # ZZZ as_of = today > fwd_cutoff (today - 5d), so it is excluded by the sig
    # CTE's date filter; even without that, LEAD(close, 5) over 2 rows is NULL.
    # Either way zero observations remain -> below _MIN_OBS -> None.
    assert result is None
