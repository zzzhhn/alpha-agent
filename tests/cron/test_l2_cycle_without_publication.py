"""QUANT-1: L2 valuation must not depend on a fresh recommendation publication.

Two layers are covered:
  * the manual workflow and the Vercel tick never gate ``l2_cycle`` on ``published``;
  * with no new research run, the continuous driver still marks existing
    holdings (stale when quotes are missing), creates no new targets, and keeps
    the original execution window (a pending intent is never filled on a later
    session's price).
"""
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
import yaml

from alpha_agent.backtest import l2_continuous, l2_driver
from alpha_agent.storage.postgres import close_pool, get_pool
from alpha_agent.storage.product_ledger import RatingSnapshot, RunMeta, record_research_run

_ROOT = Path(__file__).resolve().parents[2]


def _l2_job() -> dict:
    workflow = yaml.safe_load((_ROOT / ".github/workflows/cron-shards.yml").read_text())
    return workflow["jobs"]["l2_cycle"]


def test_l2_cycle_is_not_gated_on_publication():
    job = _l2_job()
    condition = job["if"]
    assert "published" not in condition
    # The clock moved to Vercel (tick/daily_close runs L2 after the publish
    # attempt); GitHub keeps the manual dispatch path, still preflight-gated.
    assert "github.event.schedule" not in condition
    assert job["needs"] == ["preflight", "fast_intraday"]
    assert "always()" in condition
    assert "needs.preflight.outputs.ready == 'true'" in condition
    assert "inputs.job == 'l2_cycle'" in condition


@pytest.fixture
async def pool(applied_db):
    value = await get_pool(applied_db)
    yield value
    await close_pool()


async def _seed_book(pool, *, last_fill: date) -> int:
    sid = await l2_continuous.ensure_book(pool, start_after_run_id=0)
    await pool.execute(
        "UPDATE l2_account SET cash=999000,nav=1000000,last_fill_date=$2 WHERE strategy_id=$1",
        sid, last_fill)
    await pool.execute(
        "INSERT INTO l2_position(strategy_id,ticker,qty,avg_cost,last_price,last_price_date) "
        "VALUES($1,'AAA',10,100,100,$2)", sid, last_fill)
    await pool.execute(
        "INSERT INTO l2_equity_daily(strategy_id,as_of_date,nav) VALUES($1,$2,1000000)",
        sid, last_fill)
    return sid


def _frozen(session: date):
    return lambda now=None: session


@pytest.mark.asyncio
async def test_driver_marks_without_new_publication_and_creates_no_targets(pool, monkeypatch):
    start, middle, end = date(2026, 10, 28), date(2026, 10, 29), date(2026, 10, 30)
    sid = await _seed_book(pool, last_fill=start)
    # AAA has a quote on the middle session only; the last session is stale.
    await pool.executemany(
        "INSERT INTO daily_prices(ticker,date,close) VALUES($1,$2,$3)",
        [("AAA", start, 100), ("AAA", middle, 105),
         ("SPY", start, 500), ("SPY", middle, 501), ("SPY", end, 502),
         ("RSP", start, 200), ("RSP", middle, 201), ("RSP", end, 202)])
    monkeypatch.setattr(l2_driver, "latest_completed_xnys_session", _frozen(end))

    # No research_run rows exist at all: publication never happened.
    out = await l2_driver.run_continuous_driver(pool, strategy_id=sid)

    assert out["generated"] == 0
    assert out["filled"] == 0
    assert out["valuation"]["marked"] == 2
    assert out["valuation"]["stale_marks"] == 1
    assert await pool.fetchval("SELECT count(*) FROM l2_order WHERE strategy_id=$1", sid) == 0
    marks = await pool.fetch(
        "SELECT as_of_date,stale_count FROM l2_equity_daily "
        "WHERE strategy_id=$1 AND as_of_date>$2 ORDER BY as_of_date", sid, start)
    assert [(m["as_of_date"], m["stale_count"]) for m in marks] == [(middle, 0), (end, 1)]
    # The holding survives a missing quote at its last known price.
    assert await pool.fetchval(
        "SELECT qty FROM l2_position WHERE strategy_id=$1 AND ticker='AAA'", sid) == 10


@pytest.mark.asyncio
async def test_late_job_keeps_original_execution_window(pool, monkeypatch):
    signal, fill = date(2026, 10, 28), date(2026, 10, 29)
    sid = await _seed_book(pool, last_fill=date(2026, 10, 27))
    run_id = await record_research_run(
        pool,
        RunMeta(scheduled_for_date=signal, status="complete",
                started_at=datetime(2026, 10, 28, 21, tzinfo=UTC),
                finished_at=datetime(2026, 10, 28, 21, 5, tzinfo=UTC),
                weight_policy_id="static_v2_technicals_guardrail"),
        [RatingSnapshot(ticker="BBB", tier="BUY", rank=1, eligible=True)])
    # A pending intent exists for the 10-29 session, but the job only runs after
    # later sessions closed (publication paused). No new target ladder may be
    # created, and the intent may only ever execute on 10-29 itself.
    await pool.execute(
        "INSERT INTO l2_order(strategy_id,source_run_id,signal_date,ticker,target_weight,"
        "generated_at,status) VALUES ($1,$2,$3,'BBB',0.02,$4,'pending')",
        sid, run_id, signal, datetime(2026, 10, 28, 21, 6, tzinfo=UTC))
    sessions = (date(2026, 10, 27), signal, fill, date(2026, 10, 30), date(2026, 11, 2))
    await pool.executemany(
        "INSERT INTO daily_prices(ticker,date,close) VALUES($1,$2,$3)",
        [(t, d, p) for t, p in (("AAA", 100), ("BBB", 50), ("SPY", 500), ("RSP", 200))
         for d in sessions])
    monkeypatch.setattr(l2_driver, "latest_completed_xnys_session", _frozen(date(2026, 11, 2)))

    out = await l2_driver.run_continuous_driver(pool, strategy_id=sid)

    assert out["generated"] == 0
    rows = await pool.fetch(
        "SELECT fill_date,status FROM l2_order WHERE strategy_id=$1 AND ticker='BBB'", sid)
    assert len(rows) == 1
    # Executed at its own intended session's close, not a later session.
    assert rows[0]["status"] == "filled"
    assert rows[0]["fill_date"] == fill
