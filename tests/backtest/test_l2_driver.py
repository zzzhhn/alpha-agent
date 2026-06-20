# tests/backtest/test_l2_driver.py
"""L2 driver — the scheduler that advances the paper book over the ledger
(roadmap step 6 follow-on). Given a sequence of COMPLETE gated runs + prices,
it builds a weekly-rebalanced book: rebalance on a cadence, fill at the next
trusted close, and mark each completed holding period (exit = the next
rebalance's fill), so l2_equity_daily accumulates a real forward curve.

Idempotent: re-running catches up + extends, never double-books (generate/fill
/mark are each idempotent at the engine layer).
"""
from datetime import UTC, date, datetime, timedelta

import pytest

from alpha_agent.backtest import l2_driver
from alpha_agent.storage.postgres import close_pool, get_pool
from alpha_agent.storage.product_ledger import RatingSnapshot, RunMeta, record_research_run


@pytest.fixture
async def pool(applied_db):
    p = await get_pool(applied_db)
    yield p
    await close_pool()


async def _complete_run(pool, d, picks):
    snaps = [RatingSnapshot(ticker=t, tier="BUY", rank=i + 1, eligible=True)
             for i, t in enumerate(picks)]
    meta = RunMeta(scheduled_for_date=d, status="complete",
                   started_at=datetime(2026, 6, 1, tzinfo=UTC),
                   finished_at=datetime(2026, 6, 1, 1, tzinfo=UTC))
    await record_research_run(pool, meta, snaps)


async def _seed(pool):
    # 12 contiguous trading days of prices; AAA/BBB rise, SPY rises slower.
    start = date(2026, 6, 1)
    for i in range(12):
        d = start + timedelta(days=i)
        for tk, base in [("AAA", 100.0), ("BBB", 50.0), ("SPY", 500.0)]:
            await pool.execute(
                "INSERT INTO daily_prices (ticker, date, close) VALUES ($1, $2, $3)",
                tk, d, base * (1.0 + 0.01 * i),
            )
    # complete gated runs as signal dates spaced 4 trading days apart.
    for d in (date(2026, 6, 1), date(2026, 6, 5), date(2026, 6, 9)):
        await _complete_run(pool, d, ["AAA", "BBB"])


@pytest.mark.asyncio
async def test_driver_builds_weekly_book_and_accumulates_equity(pool):
    await _seed(pool)
    sid = await l2_driver.ensure_strategy(pool, rebalance_days=3, top_n=50)
    summary = await l2_driver.run_driver(pool, strategy_id=sid, rebalance_days=3)

    # Three rebalance dates -> three order batches (each 2 names).
    batch_dates = [
        r["signal_date"]
        for r in await pool.fetch(
            "SELECT DISTINCT signal_date FROM l2_order WHERE strategy_id=$1 "
            "ORDER BY signal_date", sid
        )
    ]
    assert batch_dates == [date(2026, 6, 1), date(2026, 6, 5), date(2026, 6, 9)]

    # Two COMPLETED holding periods marked (the last batch is still open).
    equity = await pool.fetch(
        "SELECT as_of_date, gross_return, n_positions FROM l2_equity_daily "
        "WHERE strategy_id=$1 ORDER BY as_of_date", sid
    )
    assert len(equity) == 2
    for row in equity:
        assert row["n_positions"] == 2
        assert row["gross_return"] is not None
    assert summary["equity_points"] == 2


@pytest.mark.asyncio
async def test_driver_is_idempotent(pool):
    await _seed(pool)
    sid = await l2_driver.ensure_strategy(pool, rebalance_days=3, top_n=50)
    await l2_driver.run_driver(pool, strategy_id=sid, rebalance_days=3)
    orders1 = await pool.fetchval("SELECT count(*) FROM l2_order WHERE strategy_id=$1", sid)
    equity1 = await pool.fetchval("SELECT count(*) FROM l2_equity_daily WHERE strategy_id=$1", sid)

    await l2_driver.run_driver(pool, strategy_id=sid, rebalance_days=3)  # re-run
    assert await pool.fetchval("SELECT count(*) FROM l2_order WHERE strategy_id=$1", sid) == orders1
    assert await pool.fetchval("SELECT count(*) FROM l2_equity_daily WHERE strategy_id=$1", sid) == equity1


@pytest.mark.asyncio
async def test_ensure_strategy_is_idempotent(pool):
    a = await l2_driver.ensure_strategy(pool)
    b = await l2_driver.ensure_strategy(pool)
    assert a == b
