from datetime import date

import pytest

from alpha_agent.backtest.l2_continuous import ensure_book
from alpha_agent.backtest.l2_daily import mark_daily
from alpha_agent.backtest.l2_performance import performance_series
from alpha_agent.storage.postgres import close_pool, get_pool


@pytest.mark.asyncio
async def test_daily_marks_preserve_shares_cash_costs_and_idempotency(applied_db):
    pool = await get_pool(applied_db)
    try:
        sid = await ensure_book(pool, start_after_run_id=0)
        start, middle, end = date(2026, 10, 28), date(2026, 10, 29), date(2026, 10, 30)
        await pool.execute("UPDATE l2_account SET cash=999000,nav=1000000,last_fill_date=$2 WHERE strategy_id=$1", sid, start)
        await pool.execute("INSERT INTO l2_position(strategy_id,ticker,qty,avg_cost,last_price,last_price_date) VALUES($1,'AAA',10,100,100,$2)", sid, start)
        await pool.execute("INSERT INTO l2_equity_daily(strategy_id,as_of_date,nav) VALUES($1,$2,1000000)", sid, start)
        await pool.executemany("INSERT INTO daily_prices(ticker,date,close) VALUES($1,$2,$3)",
                               [(t,d,p) for t in ("AAA","SPY","RSP") for d,p in ((start,100),(middle,105),(end,110))])
        out = await mark_daily(pool, strategy_id=sid, through=end)
        assert out["marked"] == 2
        assert out["nav"] == pytest.approx(1000100)
        assert (await mark_daily(pool, strategy_id=sid, through=end))["marked"] == 0
        account = await pool.fetchrow("SELECT cash,last_fill_date FROM l2_account WHERE strategy_id=$1", sid)
        assert account["cash"] == 999000
        assert account["last_fill_date"] == start
        assert await pool.fetchval("SELECT count(*) FROM l2_order WHERE strategy_id=$1", sid) == 0
        marks = await pool.fetch("SELECT * FROM l2_equity_daily WHERE strategy_id=$1 AND as_of_date>$2 ORDER BY as_of_date", sid, start)
        assert marks[0]["net_return"] == pytest.approx(0.00005)
        assert marks[1]["benchmark_return"] == pytest.approx(110/105-1)
        # No quote on the next session: explicit stale mark, never a vanished holding.
        stale = await mark_daily(pool, strategy_id=sid, through=date(2026,11,2))
        assert stale["stale_marks"] == 1
        assert stale["nav"] == pytest.approx(1000100)
        assert await pool.fetchval("SELECT qty FROM l2_position WHERE strategy_id=$1", sid) == 10
    finally:
        await close_pool()


def test_performance_includes_entry_cost_and_leaves_gaps():
    rows = [{"as_of_date": date(2026,10,d), "nav": nav, "stale_count": 0, "missing_count": 0}
            for d,nav in ((28,999000),(30,1010000))]
    prices = {(r["as_of_date"], t): 100 for r in rows for t in ("SPY","RSP")}
    result = performance_series(rows, initial_cash=1000000, prices=prices, cost_bps=10)
    assert result["series"][0]["net"] == pytest.approx(99.9)
    assert result["series"][1]["net"] is None
    assert result["series"][1]["spy"] is None
    assert result["comparison"]["strategy"] == pytest.approx(0.01)
    assert result["comparison"]["spy"] == pytest.approx(1/1.001-1)
    assert result["missing_sessions"] == 1
    assert result["windows"]["5"]["net_return"] is None
