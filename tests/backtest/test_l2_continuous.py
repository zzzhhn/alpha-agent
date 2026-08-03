import json
from datetime import UTC, date, datetime, timedelta

import pytest

from alpha_agent.backtest import l2_continuous
from alpha_agent.storage.postgres import close_pool, get_pool
from alpha_agent.storage.product_ledger import RatingSnapshot, RunMeta, record_research_run


@pytest.fixture
async def pool(applied_db):
    value = await get_pool(applied_db)
    yield value
    await close_pool()


async def _run(pool, market_date: date, ticker: str) -> int:
    return await record_research_run(
        pool,
        RunMeta(
            scheduled_for_date=market_date,
            status="complete",
            started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
            weight_policy_id="static_v2_technicals_guardrail",
        ),
        [RatingSnapshot(ticker=ticker, tier="BUY", rank=1, eligible=True)],
    )


async def _price(pool, ticker: str, market_date: date, close: float) -> None:
    await pool.execute(
        "INSERT INTO daily_prices (ticker,date,close) VALUES ($1,$2,$3)",
        ticker,
        market_date,
        close,
    )


@pytest.mark.asyncio
async def test_continuous_book_persists_share_deltas_cash_and_costs(pool):
    signal_1 = date.today()
    fill_1 = signal_1 + timedelta(days=1)
    signal_2 = signal_1 + timedelta(days=5)
    fill_2 = signal_2 + timedelta(days=1)
    run_1 = await _run(pool, signal_1, "AAA")
    strategy_id = await l2_continuous.ensure_book(pool, start_after_run_id=0)

    created = await l2_continuous.generate_target_intent(
        pool, strategy_id=strategy_id, run_id=run_1
    )
    assert created == 1
    intent = await pool.fetchrow(
        "SELECT fill_price,target_qty,delta_qty,source_policy_id FROM l2_order "
        "WHERE strategy_id=$1 AND signal_date=$2",
        strategy_id,
        signal_1,
    )
    assert intent["fill_price"] is None
    assert intent["target_qty"] is None
    assert intent["delta_qty"] is None
    assert intent["source_policy_id"] == "static_v2_technicals_guardrail"

    await _price(pool, "AAA", fill_1, 100.0)
    first = await l2_continuous.fill_target_intent(
        pool, strategy_id=strategy_id, signal_date=signal_1, fill_date=fill_1
    )
    assert first["filled"] == 1
    first_position = await pool.fetchrow(
        "SELECT qty,avg_cost FROM l2_position WHERE strategy_id=$1 AND ticker='AAA'",
        strategy_id,
    )
    assert first_position["qty"] == 200
    assert first_position["avg_cost"] > 100.0

    run_2 = await _run(pool, signal_2, "BBB")
    assert await l2_continuous.generate_target_intent(
        pool, strategy_id=strategy_id, run_id=run_2
    ) == 2  # BBB target plus explicit AAA removal
    await _price(pool, "AAA", fill_2, 110.0)
    await _price(pool, "BBB", fill_2, 50.0)
    await _price(pool, "SPY", fill_1, 500.0)
    await _price(pool, "SPY", fill_2, 510.0)
    await _price(pool, "RSP", fill_1, 200.0)
    await _price(pool, "RSP", fill_2, 202.0)
    second = await l2_continuous.fill_target_intent(
        pool, strategy_id=strategy_id, signal_date=signal_2, fill_date=fill_2
    )
    assert second["filled"] == 2
    assert second["turnover"] > 0
    assert second["fees"] > 0

    rows = await pool.fetch(
        "SELECT ticker,qty FROM l2_position WHERE strategy_id=$1 ORDER BY ticker",
        strategy_id,
    )
    assert [(row["ticker"], row["qty"]) for row in rows] == [("AAA", 0), ("BBB", 400)]
    deltas = await pool.fetch(
        "SELECT ticker,side,pre_qty,target_qty,delta_qty,transaction_cost "
        "FROM l2_order WHERE strategy_id=$1 AND signal_date=$2 ORDER BY ticker",
        strategy_id,
        signal_2,
    )
    assert deltas[0]["side"] == "sell"
    assert deltas[0]["delta_qty"] == -200
    assert deltas[1]["side"] == "buy"
    assert deltas[1]["delta_qty"] == 400
    assert sum(float(row["transaction_cost"]) for row in deltas) > 0


@pytest.mark.asyncio
async def test_default_book_boundary_prevents_historical_backfill(pool):
    run_id = await _run(pool, date.today(), "AAA")
    strategy_id = await l2_continuous.ensure_book(pool)
    assert await l2_continuous.generate_target_intent(
        pool, strategy_id=strategy_id, run_id=run_id
    ) == 0


@pytest.mark.asyncio
async def test_tactical_and_strategic_books_are_separate_forward_accounts(pool):
    tactical = await l2_continuous.ensure_book(pool, sleeve="tactical", start_after_run_id=0)
    strategic = await l2_continuous.ensure_book(pool, sleeve="strategic", start_after_run_id=0)
    assert tactical != strategic
    rows = await pool.fetch(
        "SELECT name,params_json FROM l2_strategy WHERE id=ANY($1::bigint[]) ORDER BY name",
        [tactical, strategic],
    )
    params = {
        row["name"]: (json.loads(row["params_json"]) if isinstance(row["params_json"], str) else row["params_json"])
        for row in rows
    }
    assert params["canonical_top50_continuous"]["policy_id"] == "static_v2_technicals_guardrail"
    assert params["canonical_top50_continuous_strategic"]["policy_id"] == "strategic_v1_60d_frozen"
