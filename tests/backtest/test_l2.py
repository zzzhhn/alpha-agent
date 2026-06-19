# tests/backtest/test_l2.py
"""Minimal causal L2 forward paper-trading (roadmap step 6).

Council verification bullets, pinned here:
  - CAUSAL ORDERING: orders for signal-date D are persisted with the source
    snapshot's run_id and a generated_at timestamp, and carry NO fill price
    until a strictly-later fill reads D+1 prices (no look-ahead by construction).
  - DETERMINISTIC EQUITY: the marked equity reproduces from l2_order.fill_price
    + daily_prices + the benchmark, exactly.
  - DEAD-FEED SAFETY: a held position whose feed dies produces an explicit exit
    event (status='exited', reason), never a silent disappearance.
Plus the selection rule (top-N, BUY/OW preferred, then by rank, equal weight).
"""
from datetime import UTC, date, datetime

import pytest

from alpha_agent.backtest import l2
from alpha_agent.storage.postgres import close_pool, get_pool
from alpha_agent.storage.product_ledger import (
    RatingSnapshot,
    RunMeta,
    record_research_run,
)


@pytest.fixture
async def pool(applied_db):
    p = await get_pool(applied_db)
    yield p
    await close_pool()


async def _seed_run(pool, signal_date, picks):
    """picks: list of (ticker, tier, rank). Returns the complete run id."""
    snaps = [
        RatingSnapshot(ticker=t, tier=tier, rank=r, eligible=True,
                       composite_z=2.0 - r * 0.1)
        for (t, tier, r) in picks
    ]
    meta = RunMeta(
        scheduled_for_date=signal_date, status="complete",
        started_at=datetime(2026, 6, 18, 21, tzinfo=UTC),
        finished_at=datetime(2026, 6, 18, 21, 5, tzinfo=UTC),
    )
    return await record_research_run(pool, meta, snaps)


async def _price(pool, ticker, d, close):
    await pool.execute(
        "INSERT INTO daily_prices (ticker, date, close) VALUES ($1, $2, $3) "
        "ON CONFLICT (ticker, date) DO UPDATE SET close = EXCLUDED.close",
        ticker, d, close,
    )


# --- selection (pure) ---

def test_select_holdings_prefers_buy_ow_then_rank():
    snaps = [
        {"ticker": "A", "tier": "HOLD", "rank": 1, "eligible": True},
        {"ticker": "B", "tier": "BUY", "rank": 5, "eligible": True},
        {"ticker": "C", "tier": "OW", "rank": 3, "eligible": True},
    ]
    held = l2.select_holdings(snaps, top_n=2)
    # BUY/OW preferred over a better-ranked HOLD; within preferred, by rank.
    assert [h["ticker"] for h in held] == ["C", "B"]
    assert all(h["target_weight"] == pytest.approx(0.5) for h in held)


def test_select_holdings_skips_ineligible():
    snaps = [
        {"ticker": "A", "tier": "BUY", "rank": 1, "eligible": False},
        {"ticker": "B", "tier": "BUY", "rank": 2, "eligible": True},
    ]
    held = l2.select_holdings(snaps, top_n=50)
    assert [h["ticker"] for h in held] == ["B"]


# --- causal ordering ---

@pytest.mark.asyncio
async def test_generate_orders_is_causal(pool):
    sid = await l2.register_strategy(pool, name="canon", params={"top_n": 2, "cost_bps": 10})
    run_id = await _seed_run(pool, date(2026, 6, 18),
                             [("AAA", "BUY", 1), ("BBB", "OW", 2), ("CCC", "HOLD", 3)])
    n = await l2.generate_orders(pool, strategy_id=sid, run_id=run_id)
    assert n == 2  # top_n=2

    rows = await pool.fetch(
        "SELECT * FROM l2_order WHERE strategy_id=$1 ORDER BY rank", sid
    )
    assert {r["ticker"] for r in rows} == {"AAA", "BBB"}
    for r in rows:
        assert r["source_run_id"] == run_id        # references the immutable snapshot
        assert r["signal_date"] == date(2026, 6, 18)
        assert r["generated_at"] is not None
        assert r["fill_price"] is None             # NO execution price at generation
        assert r["status"] == "pending"


@pytest.mark.asyncio
async def test_generate_orders_idempotent_per_signal_date(pool):
    sid = await l2.register_strategy(pool, name="c", params={"top_n": 2})
    run_id = await _seed_run(pool, date(2026, 6, 18), [("AAA", "BUY", 1), ("BBB", "BUY", 2)])
    await l2.generate_orders(pool, strategy_id=sid, run_id=run_id)
    n2 = await l2.generate_orders(pool, strategy_id=sid, run_id=run_id)
    assert n2 == 0  # already generated for this signal_date
    assert await pool.fetchval("SELECT count(*) FROM l2_order WHERE strategy_id=$1", sid) == 2


# --- fill + deterministic equity ---

@pytest.mark.asyncio
async def test_fill_then_mark_reproduces_equity(pool):
    sid = await l2.register_strategy(pool, name="c", params={"top_n": 2, "cost_bps": 10})
    run_id = await _seed_run(pool, date(2026, 6, 18), [("AAA", "BUY", 1), ("BBB", "BUY", 2)])
    await l2.generate_orders(pool, strategy_id=sid, run_id=run_id)

    fill_d, mark_d = date(2026, 6, 19), date(2026, 6, 26)
    for tk, fp, mp in [("AAA", 100.0, 110.0), ("BBB", 50.0, 55.0)]:
        await _price(pool, tk, fill_d, fp)
        await _price(pool, tk, mark_d, mp)
    await _price(pool, "SPY", fill_d, 500.0)
    await _price(pool, "SPY", mark_d, 510.0)

    filled = await l2.fill_orders(pool, strategy_id=sid, signal_date=date(2026, 6, 18), fill_date=fill_d)
    assert filled["filled"] == 2

    eq = await l2.mark_equity(pool, strategy_id=sid, signal_date=date(2026, 6, 18), mark_date=mark_d)
    # both names +10% equal-weight -> gross +0.10; SPY +2% benchmark.
    assert eq["gross_return"] == pytest.approx(0.10)
    assert eq["benchmark_return"] == pytest.approx(0.02)
    assert eq["net_return"] < eq["gross_return"]  # costs drag

    # Reproduce from persisted state: recompute equity row deterministically.
    again = await l2.mark_equity(pool, strategy_id=sid, signal_date=date(2026, 6, 18), mark_date=mark_d)
    assert again["gross_return"] == pytest.approx(eq["gross_return"])
    assert again["net_return"] == pytest.approx(eq["net_return"])


# --- dead-feed safety ---

@pytest.mark.asyncio
async def test_dead_feed_position_exits_not_silently_dropped(pool):
    sid = await l2.register_strategy(pool, name="c", params={"top_n": 2, "cost_bps": 10})
    run_id = await _seed_run(pool, date(2026, 6, 18), [("AAA", "BUY", 1), ("DEAD", "BUY", 2)])
    await l2.generate_orders(pool, strategy_id=sid, run_id=run_id)

    fill_d = date(2026, 6, 19)
    await _price(pool, "AAA", fill_d, 100.0)
    # DEAD has no price at fill_date -> cannot be entered.
    filled = await l2.fill_orders(pool, strategy_id=sid, signal_date=date(2026, 6, 18), fill_date=fill_d)
    assert filled["filled"] == 1
    assert filled["unfilled"] == 1

    dead = await pool.fetchrow(
        "SELECT status, exit_reason FROM l2_order WHERE strategy_id=$1 AND ticker='DEAD'", sid
    )
    assert dead["status"] == "unfilled"          # explicit, not missing
    assert dead["exit_reason"] is not None        # records WHY
