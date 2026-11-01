import json
from datetime import UTC, date, datetime, timedelta

import pytest

from alpha_agent.backtest import l2_continuous
from alpha_agent.market_session import next_xnys_session, xnys_close
from alpha_agent.storage.postgres import close_pool, get_pool
from alpha_agent.storage.product_ledger import RatingSnapshot, RunMeta, record_research_run


@pytest.fixture
async def pool(applied_db):
    value = await get_pool(applied_db)
    yield value
    await close_pool()


async def _run(pool, market_date: date, ticker: str, *, allow_correction: bool = False) -> int:
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
        allow_correction=allow_correction,
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
    fill_1 = next_xnys_session(signal_1)
    signal_2 = signal_1 + timedelta(days=5)
    fill_2 = next_xnys_session(signal_2)
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
async def test_same_utc_day_intent_before_us_close_executes(pool):
    signal = date(2026, 8, 31)
    fill = date(2026, 9, 1)
    rid = await _run(pool, signal, "AAA")
    sid = await l2_continuous.ensure_book(pool, start_after_run_id=0)
    await l2_continuous.generate_target_intent(pool, strategy_id=sid, run_id=rid)
    await pool.execute("UPDATE l2_order SET generated_at=$1 WHERE strategy_id=$2",
                       datetime(2026, 9, 1, 2, tzinfo=UTC), sid)
    await _price(pool, "AAA", fill, 100)
    result = await l2_continuous.fill_target_intent(pool, strategy_id=sid, signal_date=signal, fill_date=fill)
    assert result["filled"] == 1
    assert await pool.fetchval("SELECT last_fill_date FROM l2_account WHERE strategy_id=$1", sid) == fill


@pytest.mark.asyncio
async def test_after_close_intent_and_retrograde_order_are_terminal(pool):
    signal = date(2026, 8, 31)
    fill = date(2026, 9, 1)
    rid = await _run(pool, signal, "AAA")
    sid = await l2_continuous.ensure_book(pool, start_after_run_id=0)
    await l2_continuous.generate_target_intent(pool, strategy_id=sid, run_id=rid)
    await pool.execute("UPDATE l2_order SET generated_at=$1 WHERE strategy_id=$2", xnys_close(fill), sid)
    result = await l2_continuous.fill_target_intent(pool, strategy_id=sid, signal_date=signal, fill_date=fill)
    assert result["reason"] == "intent_after_execution_close"
    assert result["unfilled"] == 1
    assert await pool.fetchval("SELECT nav FROM l2_account WHERE strategy_id=$1", sid) == 1_000_000
    await pool.execute("UPDATE l2_order SET status='pending' WHERE strategy_id=$1", sid)
    await pool.execute("UPDATE l2_account SET last_fill_date=$1 WHERE strategy_id=$2", fill, sid)
    result = await l2_continuous.fill_target_intent(pool, strategy_id=sid, signal_date=signal, fill_date=fill)
    assert result["reason"] == "superseded_by_account_progress"


def test_exchange_close_handles_holidays_and_early_close():
    assert next_xnys_session(date(2026, 9, 4)) == date(2026, 9, 8)
    assert xnys_close(date(2026, 11, 27)).hour == 18


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


@pytest.mark.asyncio
async def test_tactical_restart_preserves_old_book_and_uses_new_session_boundary(pool, monkeypatch):
    from alpha_agent.api.routes.l2 import _continuous_account
    from alpha_agent.backtest.l2_driver import run_continuous_driver

    class Clock(datetime):
        current = datetime(2026, 11, 1, 12, tzinfo=UTC)

        @classmethod
        def now(cls, tz=None):
            return cls.current

    monkeypatch.setattr(l2_continuous, "datetime", Clock)
    prior_run = await _run(pool, date(2026, 10, 30), "AAA")
    old = await pool.fetchval(
        "INSERT INTO l2_strategy(name,version,params_json) "
        "VALUES ('canonical_top50_continuous',2,'{}') RETURNING id")
    await pool.execute(
        "INSERT INTO l2_account(strategy_id,initial_cash,cash,nav,start_after_run_id) "
        "VALUES ($1,1000000,250000,980000,0)", old)
    await pool.execute(
        "INSERT INTO l2_order(strategy_id,source_run_id,signal_date,ticker,target_weight,generated_at,status) "
        "VALUES ($1,$2,'2026-09-15','PARA',0.02,now(),'filled')", old, prior_run)
    await pool.execute(
        "INSERT INTO l2_position(strategy_id,ticker,qty,avg_cost) VALUES ($1,'PARA',10,3)", old)
    strategic = await l2_continuous.ensure_book(pool, sleeve="strategic")
    old_before = dict(await pool.fetchrow("SELECT * FROM l2_account WHERE strategy_id=$1", old))
    strategic_before = dict(await pool.fetchrow("SELECT * FROM l2_account WHERE strategy_id=$1", strategic))

    fresh = await l2_continuous.ensure_book(pool)
    assert fresh not in (old, strategic)
    assert await l2_continuous.generate_target_intent(pool, strategy_id=fresh, run_id=prior_run) == 0
    # A freshly published run for an OLD session is still not a forward signal.
    repeated_old_day = await _run(pool, date(2026, 10, 30), "AAA", allow_correction=True)
    assert await l2_continuous.generate_target_intent(pool, strategy_id=fresh, run_id=repeated_old_day) == 0
    account = await _continuous_account(pool, strategy_name="canonical_top50_continuous")
    assert account["strategy_id"] == fresh
    assert account["strategy_version"] == 3
    assert account["status"] == "awaiting_forward_run"
    assert account["not_before_signal_date"] == "2026-11-02"
    assert account["replaces_strategy_id"] == old
    assert account["positions"] == account["pending_orders"] == 0
    assert account["cash"] == account["nav"] == 1_000_000

    future_run = await _run(pool, date(2026, 11, 2), "AAA")
    assert await l2_continuous.generate_target_intent(pool, strategy_id=fresh, run_id=future_run) == 1
    assert next_xnys_session(date(2026, 11, 2)) == date(2026, 11, 3)
    Clock.current = datetime(2026, 11, 4, 12, tzinfo=UTC)
    assert await l2_continuous.ensure_book(pool) == fresh
    assert await l2_continuous.ensure_book(pool, sleeve="strategic") == strategic
    after = await _continuous_account(pool, strategy_name="canonical_top50_continuous")
    assert after["not_before_signal_date"] == "2026-11-02"
    assert after["start_after_run_id"] == prior_run
    assert dict(await pool.fetchrow("SELECT * FROM l2_account WHERE strategy_id=$1", old)) == old_before
    assert dict(await pool.fetchrow("SELECT * FROM l2_account WHERE strategy_id=$1", strategic)) == strategic_before
    assert await pool.fetchval("SELECT qty FROM l2_position WHERE strategy_id=$1 AND ticker='PARA'", old) == 10
    assert (await run_continuous_driver(pool, strategy_id=old))["status"] == "identity_quarantined"
