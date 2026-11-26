"""Synthetic market order admission and exact-close review on isolated Postgres."""
from datetime import UTC, date, datetime

import asyncpg
import pytest
from fastapi import HTTPException

from alpha_agent.api.routes import paper
from alpha_agent.api.routes.cron_routes import _run_paper_fill_locked

SIGNAL = date(2026, 7, 13)
TARGET = date(2026, 7, 14)
DEADLINE = date(2026, 7, 15)


class FixedClock(datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 7, 13, 21, tzinfo=UTC)


async def test_admission_requires_exact_completed_quote_and_resolved_identity(applied_db, monkeypatch):
    async with asyncpg.create_pool(applied_db, min_size=1, max_size=2) as pool:
        uid = await pool.fetchval("INSERT INTO users(email) VALUES('quotes@test.example') RETURNING id")

        async def db():
            return pool

        monkeypatch.setattr(paper, 'get_db_pool', db)
        monkeypatch.setattr(paper, 'datetime', FixedClock)
        await pool.execute("INSERT INTO sim_instrument(ticker,identity_status) VALUES('OLD','renamed')")
        await pool.executemany(
            "INSERT INTO daily_prices(ticker,date,close) VALUES($1,$2,$3)",
            [('OLD', SIGNAL, 100), ('PARA', SIGNAL, 100), ('STALE', date(2026, 7, 10), 100),
             ('STALE', TARGET, 100), ('NEW', SIGNAL, 120)],
        )
        for ticker in ('STALE', 'OLD', 'PARA'):
            with pytest.raises(HTTPException) as rejected:
                await paper.place_order(paper.PlaceOrderRequest(ticker=ticker, side='buy', order_type='market', qty=1), uid)
            assert rejected.value.status_code == 400 and ticker in str(rejected.value.detail)
        assert await pool.fetchval("SELECT COUNT(*) FROM sim_order") == 0

        order = await paper.place_order(
            paper.PlaceOrderRequest(ticker='NEW', side='buy', order_type='market', qty=2), uid,
        )
        saved = await pool.fetchrow(
            "SELECT reference_price,reserved_notional,instrument_id,expires_at FROM sim_order WHERE id=$1",
            order.order_id,
        )
        assert saved['reference_price'] == 120 and saved['reserved_notional'] == pytest.approx(240.24)
        assert saved['instrument_id'] == await pool.fetchval("SELECT id FROM sim_instrument WHERE ticker='NEW'")
        assert saved['expires_at'] == datetime(2026, 7, 15, 20, tzinfo=UTC)


async def test_market_review_waits_for_exact_close_then_releases_reservations(applied_db, monkeypatch):
    async with asyncpg.create_pool(applied_db, min_size=1, max_size=2) as pool:
        uid = await pool.fetchval("INSERT INTO users(email) VALUES('review@test.example') RETURNING id")
        aid = await pool.fetchval(
            "INSERT INTO sim_account(user_id,initial_cash,cash,created_at) "
            "VALUES($1,1000,1000,'2026-07-10') RETURNING id", uid,
        )

        async def db():
            return pool

        monkeypatch.setattr(paper, 'get_db_pool', db)
        await pool.execute(
            "INSERT INTO sim_order(account_id,ticker,side,order_type,qty,signal_date,reserved_notional) "
            "SELECT $1,ticker,'buy','market',1,$2,100.1 "
            "FROM unnest(ARRAY['LATE','MISSING','CANCEL','MOVE']) AS ticker", aid, SIGNAL,
        )
        await pool.execute(
            "INSERT INTO daily_prices(ticker,date,close) VALUES('MISSING',$1,25)", DEADLINE,
        )
        now = datetime(2026, 7, 14, 21, tzinfo=UTC)
        await _run_paper_fill_locked(pool, TARGET)
        account = await paper._read_account(pool, uid, aid, now=now)
        assert account.cash == 1000 and account.reserved_cash == pytest.approx(400.40)
        assert account.valuation_quality == 'orders_pending'
        orders = {row.ticker: row for row in (await paper._read_orders(pool, uid, account_id=aid)).orders}
        assert orders['MISSING'].status == 'pending'
        assert orders['MISSING'].fail_reason == 'market_awaiting_exact_t1_close'
        assert orders['MISSING'].execution_evidence['target_session_date'] == TARGET.isoformat()
        assert orders['MISSING'].execution_evidence['quote_deadline_session_date'] == DEADLINE.isoformat()
        assert (await paper.cancel_order(orders['CANCEL'].id, uid)).status_code == 204

        await pool.execute("INSERT INTO sim_instrument(ticker,identity_status) VALUES('MOVE','renamed')")
        counts = await _run_paper_fill_locked(pool, TARGET)
        assert (counts['filled'], counts['failed'], counts['remaining_pending']) == (0, 1, 2)
        account = await paper._read_account(pool, uid, aid, now=now)
        assert account.cash == 1000 and account.reserved_cash == pytest.approx(200.20)

        await pool.execute(
            "INSERT INTO daily_prices(ticker,date,close) VALUES('LATE',$1,110),('MOVE',$1,100)", TARGET,
        )
        counts = await _run_paper_fill_locked(pool, DEADLINE)
        assert (counts['filled'], counts['expired'], counts['failed'], counts['remaining_pending']) == (1, 1, 0, 0)
        orders = {row.ticker: row for row in (await paper._read_orders(pool, uid, account_id=aid)).orders}
        assert (orders['LATE'].status, orders['LATE'].fill_date, orders['LATE'].fill_price) == (
            'filled', TARGET.isoformat(), 110,
        )
        assert orders['LATE'].fail_reason is None and orders['LATE'].transaction_cost == pytest.approx(0.11)
        assert (orders['MISSING'].status, orders['MISSING'].fail_reason) == ('expired', 'market_expired_missing_t1_close')
        assert (orders['MOVE'].status, orders['MOVE'].fail_reason) == ('failed', 'market_identity_unresolved')
        assert orders['CANCEL'].status == 'cancelled' and orders['CANCEL'].fail_reason is None
        await pool.execute("INSERT INTO daily_prices(ticker,date,close) VALUES('MISSING',$1,95)", TARGET)
        assert (await _run_paper_fill_locked(pool, date(2026, 7, 16)))['filled'] == 0
        account = await paper._read_account(pool, uid, aid, now=datetime(2026, 7, 15, 21, tzinfo=UTC))
        assert account.available_cash == account.cash == pytest.approx(889.89)
        assert account.reserved_cash == 0 and [p.ticker for p in account.positions] == ['LATE']
