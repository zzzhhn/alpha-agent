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


@pytest.mark.asyncio
async def test_ic_respects_custom_horizon(pool):
    # council #4: at horizon_days=3 the return is encoded in the 4th close
    # (LEAD 3 rows ahead), not the 6th. Monotone z -> Spearman ~1.0.
    base = date.today() - timedelta(days=40)
    for k in range(12):
        z = (k - 5.5) / 6.0
        exit_close = 100.0 * (1.0 + z * 0.1)
        await _seed(
            pool, f"H{k:02d}", base, z=z,
            closes=[100, 100, 100, exit_close],  # LEAD(3) -> index 3
        )
    result = await compute_walk_forward_ic(pool, "factor", 90, horizon_days=3)
    assert result is not None
    ic, n_obs = result
    assert n_obs >= 10
    assert ic > 0.99


async def _seed_dated(pool, ticker, as_of, z, dated_closes):
    """Like _seed but with explicit (date, close) rows so we can inject gaps."""
    await pool.execute(
        "INSERT INTO daily_signals_fast (ticker, date, composite, breakdown, fetched_at) "
        "VALUES ($1,$2,0.0,$3::jsonb,now()) "
        "ON CONFLICT (ticker, date) DO UPDATE SET breakdown = EXCLUDED.breakdown",
        ticker, as_of, json.dumps({"breakdown": [{"signal": "factor", "z": z}]}),
    )
    for d, c in dated_closes:
        await pool.execute(
            "INSERT INTO daily_prices (ticker, date, close) VALUES ($1,$2,$3) "
            "ON CONFLICT (ticker, date) DO UPDATE SET close = EXCLUDED.close",
            ticker, d, c,
        )


@pytest.mark.asyncio
async def test_span_guard_excludes_gapped_exit(pool):
    # council #3: LEAD counts ROWS not calendar days. If missing rows stretch
    # the 5th-ahead close to 40 days out (>> the ~14d cap for horizon 5), the
    # exit price is stale and must be excluded even though it is non-NULL.
    base = date.today() - timedelta(days=80)
    for k in range(12):
        z = (k - 5.5) / 6.0
        exit_close = 100.0 * (1.0 + z * 0.1)
        # 5 consecutive rows then a 6th (LEAD-5 exit) 40 days later -> gap.
        dated = [(base + timedelta(days=i), 100.0) for i in range(5)]
        dated.append((base + timedelta(days=40), exit_close))
        await _seed_dated(pool, f"G{k:02d}", base, z, dated)
    result = await compute_walk_forward_ic(pool, "factor", 90, horizon_days=5)
    # every exit is 40 calendar days out (> 5*2+4=14), so all are dropped by the
    # span guard -> 0 observations -> None.
    assert result is None
