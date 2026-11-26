"""Integration test for the paper_fill cron against a real test DB."""
import pytest
import asyncpg
from datetime import date, timedelta
from pathlib import Path


@pytest.mark.asyncio
async def test_paper_fill_market_order_fills_at_t1(applied_db):
    """A market order submitted today fills at T+1 close price."""
    conn = await asyncpg.connect(applied_db)
    try:
        # Seed: user, account, a market order for AAPL
        user_id = await conn.fetchval(
            "INSERT INTO users (email) VALUES ('fill@test.com') RETURNING id"
        )
        acct_id = await conn.fetchval(
            "INSERT INTO sim_account (user_id) VALUES ($1) RETURNING id", user_id
        )
        signal_date = date(2026, 7, 10)
        order_id = await conn.fetchval(
            """INSERT INTO sim_order
               (account_id, ticker, side, order_type, qty, signal_date)
               VALUES ($1, 'AAPL', 'buy', 'market', 10, $2) RETURNING id""",
            acct_id, signal_date,
        )
        # Seed: T+1 price
        fill_date = date(2026, 7, 13)  # Monday after the Friday signal
        await conn.execute(
            "INSERT INTO daily_prices (ticker, date, close) VALUES ('AAPL', $1, 185.0) "
            "ON CONFLICT DO NOTHING", fill_date
        )

        from alpha_agent.api.routes.cron_routes import _run_paper_fill
        result = await _run_paper_fill(applied_db)
        assert result["filled"] >= 1

        order = await conn.fetchrow("SELECT * FROM sim_order WHERE id = $1", order_id)
        assert order["status"] == "filled"
        assert order["fill_price"] == pytest.approx(185.0)
        assert order["fill_date"] == fill_date

        # Cash should be reduced
        acct = await conn.fetchrow("SELECT cash FROM sim_account WHERE id = $1", acct_id)
        assert acct["cash"] == pytest.approx(1000000.0 - 185.0 * 10 * 1.001)

        # Position should exist
        pos = await conn.fetchrow(
            "SELECT * FROM sim_position WHERE account_id = $1 AND ticker = 'AAPL'", acct_id
        )
        assert pos is not None
        assert pos["qty"] == 10
        assert pos["avg_cost"] == pytest.approx(185.0 * 1.001)
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_paper_fill_limit_order_expires(applied_db):
    """A buy limit order expires after expire_after_days trading days without crossing."""
    conn = await asyncpg.connect(applied_db)
    try:
        user_id = await conn.fetchval(
            "INSERT INTO users (email) VALUES ('expire@test.com') RETURNING id"
        )
        acct_id = await conn.fetchval(
            "INSERT INTO sim_account (user_id) VALUES ($1) RETURNING id", user_id
        )
        signal_date = date(2026, 7, 7)
        await conn.fetchval(
            """INSERT INTO sim_order
               (account_id, ticker, side, order_type, qty, limit_price, signal_date, expire_after_days)
               VALUES ($1, 'NVDA', 'buy', 'limit', 5, 120.0, $2, 3) RETURNING id""",
            acct_id, signal_date,
        )
        # 3 days of prices, all above 120 (buy limit won't cross)
        for i, price in enumerate([125.0, 126.0, 127.0], start=1):
            await conn.execute(
                "INSERT INTO daily_prices (ticker, date, close) VALUES ('NVDA', $1, $2) "
                "ON CONFLICT DO NOTHING",
                signal_date + timedelta(days=i), price,
            )

        from alpha_agent.api.routes.cron_routes import _run_paper_fill
        result = await _run_paper_fill(applied_db)
        assert result["expired"] >= 1

        order = await conn.fetchrow(
            "SELECT status FROM sim_order WHERE account_id = $1", acct_id
        )
        assert order["status"] == "expired"
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_three_session_limit_outcomes_and_reservations(applied_db):
    from alpha_agent.api.routes.cron_routes import _run_paper_fill_locked
    from alpha_agent.api.routes.paper import _read_account, _read_orders

    signal = date(2026, 7, 13)
    first, second, last = (signal + timedelta(days=i) for i in (1, 2, 3))
    pool = await asyncpg.create_pool(applied_db, min_size=1, max_size=2)
    try:
        async with pool.acquire() as conn:
            uid = await conn.fetchval("INSERT INTO users(email) VALUES ('limit-window@example.test') RETURNING id")
            aid = await conn.fetchval(
                "INSERT INTO sim_account(user_id,initial_cash,cash) VALUES ($1,1000,1000) RETURNING id",
                uid,
            )
            await conn.execute(
                "INSERT INTO sim_order(account_id,ticker,side,order_type,qty,signal_date,"
                "limit_price,expire_after_days,reserved_notional) "
                "SELECT $1,ticker,'buy','limit',1,$2,100,3,100.10 "
                "FROM unnest(ARRAY['GAP','NO_CROSS','CROSS']) AS ticker",
                aid, signal,
            )
            await conn.executemany(
                "INSERT INTO daily_prices(ticker,date,close) VALUES ($1,$2,$3)",
                [("GAP", first, 101), ("GAP", last, 100),
                 ("GAP", last + timedelta(days=1), 99),  # Outside the window.
                 ("NO_CROSS", first, 101), ("NO_CROSS", second, 102), ("NO_CROSS", last, 100),
                 ("CROSS", first, 101), ("CROSS", last, 99)],
            )
        before = await _run_paper_fill_locked(pool, second)
        assert (before["filled"], before["expired"], before["remaining_pending"]) == (0, 0, 3)
        account = await _read_account(pool, uid, aid)
        assert account.cash == 1000
        assert account.reserved_cash == pytest.approx(300.30)

        result = await _run_paper_fill_locked(pool, last)
        assert (result["filled"], result["expired"], result["remaining_pending"]) == (1, 2, 0)
        orders = {order.ticker: order for order in (await _read_orders(pool, uid, account_id=aid)).orders}
        assert (orders["CROSS"].status, orders["CROSS"].fill_date, orders["CROSS"].fill_price) == (
            "filled", last.isoformat(), 100,
        )
        assert orders["CROSS"].transaction_cost == pytest.approx(0.10)
        assert (orders["NO_CROSS"].status, orders["NO_CROSS"].fail_reason) == (
            "expired", "limit_expired_no_cross",
        )
        assert (orders["GAP"].status, orders["GAP"].fail_reason) == (
            "expired", "limit_expired_missing_quotes",
        )
        assert orders["GAP"].execution_evidence["missing_quote_dates"] == [second.isoformat()]
        assert orders["NO_CROSS"].execution_evidence["missing_quote_dates"] == []
        account = await _read_account(pool, uid, aid)
        assert account.reserved_cash == 0
        assert account.available_cash == account.cash == pytest.approx(899.90)
        assert [(row.ticker, row.qty, row.avg_cost) for row in account.positions] == [("CROSS", 1, 100.10)]
    finally:
        await pool.close()


@pytest.mark.asyncio
async def test_no_quote_expiry_and_cross_are_not_starved_by_missing_market_quotes(applied_db):
    from alpha_agent.api.routes.cron_routes import _run_paper_fill_locked

    pool = await asyncpg.create_pool(applied_db, min_size=1, max_size=2)
    try:
        async with pool.acquire() as conn:
            uid = await conn.fetchval("INSERT INTO users(email) VALUES ('backlog@test.com') RETURNING id")
            aid = await conn.fetchval("INSERT INTO sim_account(user_id) VALUES ($1) RETURNING id", uid)
            await conn.execute(
                "INSERT INTO sim_order(account_id,ticker,side,order_type,qty,signal_date) "
                "SELECT $1,'STALE','buy','market',1,$2 FROM generate_series(1,205)",
                aid, date(2026, 7, 2),
            )
            await conn.execute(
                "INSERT INTO sim_order(account_id,ticker,side,order_type,qty,signal_date,limit_price,expire_after_days) "
                "VALUES ($1,'MISSING','buy','limit',1,$2,100,2), "
                "       ($1,'CROSS','buy','limit',1,$2,100,2), "
                "       ($1,'LATE','buy','limit',1,$2,100,2)",
                aid, date(2026, 7, 2),
            )
            await conn.executemany(
                "INSERT INTO daily_prices(ticker,date,close) VALUES ($1,$2,$3)",
                [
                    ("STALE", date(2026, 7, 3), 99.0),  # market holiday
                    ("STALE", date(2026, 7, 7), 99.0),  # not exact T+1
                    ("CROSS", date(2026, 7, 7), 99.0),  # last eligible close
                    ("LATE", date(2026, 7, 8), 99.0),  # after the expiry window
                ],
            )
        result = await _run_paper_fill_locked(pool, date(2026, 7, 8))
        assert (result["filled"], result["expired"], result["remaining_pending"]) == (1, 2, 205)
        assert result["market_pending_policy"] == "await_exact_t1_close"
        rows = await pool.fetch(
            "SELECT ticker,status,fill_date,fill_price FROM sim_order WHERE order_type='limit' ORDER BY ticker"
        )
        assert [tuple(row) for row in rows] == [
            ("CROSS", "filled", date(2026, 7, 7), 100.0),
            ("LATE", "expired", None, None),
            ("MISSING", "expired", None, None),
        ]
    finally:
        await pool.close()


@pytest.mark.asyncio
async def test_paper_fill_skips_when_another_invocation_holds_job_lock(applied_db):
    """The second invocation returns immediately instead of doubling DB work."""
    conn = await asyncpg.connect(applied_db)
    try:
        await conn.fetchval(
            "SELECT pg_advisory_lock(hashtext($1))",
            "alpha_agent.paper_fill",
        )

        from alpha_agent.api.routes.cron_routes import _run_paper_fill

        result = await _run_paper_fill(applied_db)
        assert result == {
            "ok": True,
            "skipped": True,
            "reason": "already_running",
            "filled": 0,
            "expired": 0,
            "failed": 0,
        }
    finally:
        await conn.fetchval(
            "SELECT pg_advisory_unlock(hashtext($1))",
            "alpha_agent.paper_fill",
        )
        await conn.close()


@pytest.mark.asyncio
async def test_paper_fill_skips_a_row_locked_by_another_worker(applied_db):
    """Per-order SKIP LOCKED is a defensive second concurrency boundary."""
    conn = await asyncpg.connect(applied_db)
    try:
        user_id = await conn.fetchval(
            "INSERT INTO users (email) VALUES ('locked-fill@test.com') RETURNING id"
        )
        acct_id = await conn.fetchval(
            "INSERT INTO sim_account (user_id) VALUES ($1) RETURNING id", user_id
        )
        signal_date = date(2026, 7, 10)
        order_id = await conn.fetchval(
            """INSERT INTO sim_order
               (account_id, ticker, side, order_type, qty, signal_date)
               VALUES ($1, 'MSFT', 'buy', 'market', 1, $2) RETURNING id""",
            acct_id,
            signal_date,
        )
        await conn.execute(
            "INSERT INTO daily_prices (ticker, date, close) VALUES ('MSFT', $1, 420.0)",
            date(2026, 7, 13),
        )

        async with conn.transaction():
            await conn.fetchrow("SELECT id FROM sim_order WHERE id=$1 FOR UPDATE", order_id)

            from alpha_agent.api.routes.cron_routes import _run_paper_fill

            result = await _run_paper_fill(applied_db)
            assert result["filled"] == 0
            assert result["skipped_locked"] == 1

        status = await conn.fetchval("SELECT status FROM sim_order WHERE id=$1", order_id)
        assert status == "pending"
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_equity_snapshot_includes_closed_realized_pnl_in_one_aggregate(applied_db):
    conn = await asyncpg.connect(applied_db)
    try:
        user_id = await conn.fetchval(
            "INSERT INTO users (email) VALUES ('snapshot-pnl@test.com') RETURNING id"
        )
        acct_id = await conn.fetchval(
            "INSERT INTO sim_account (user_id,cash,created_at) VALUES ($1,1000.0,'2026-07-10') RETURNING id",
            user_id,
        )
        await conn.execute(
            "INSERT INTO sim_position (account_id, ticker, qty, avg_cost, realized_pnl) "
            "VALUES ($1, 'AAPL', 0, 100.0, 500.0), "
            "       ($1, 'MSFT', 2, 100.0, 75.0)",
            acct_id,
        )
        await conn.execute(
            "INSERT INTO daily_prices (ticker, date, close) VALUES ('MSFT', $1, 110.0)",
            date(2026, 7, 13),
        )

        from alpha_agent.api.routes.cron_routes import _write_paper_equity_snapshots

        as_of = date(2026, 7, 13)
        await _write_paper_equity_snapshots(conn, as_of)
        snapshot = await conn.fetchrow(
            "SELECT * FROM sim_equity_daily WHERE account_id=$1 AND as_of_date=$2",
            acct_id,
            as_of,
        )
        assert snapshot["portfolio_value"] == pytest.approx(1220.0)
        assert snapshot["unrealized_pnl"] == pytest.approx(20.0)
        assert snapshot["realized_pnl"] == pytest.approx(575.0)
    finally:
        await conn.close()


async def test_human_valuation_distinguishes_daily_marks_and_benchmark_gap(applied_db):
    from datetime import UTC, datetime

    from alpha_agent.api.routes.cron_routes import _run_paper_fill_locked
    from alpha_agent.api.routes.paper import _read_account, _read_equity_curve

    day = date(2026, 7, 14)
    prior = date(2026, 7, 13)
    as_of = datetime(2026, 7, 14, 21, tzinfo=UTC)
    async with asyncpg.create_pool(applied_db, min_size=1, max_size=2) as pool:
        uid = await pool.fetchval("INSERT INTO users(email) VALUES('marks@test.example') RETURNING id")
        aid = await pool.fetchval(
            "INSERT INTO sim_account(user_id,initial_cash,cash,created_at) "
            "VALUES($1,1000,800,$2) RETURNING id", uid, datetime(2026, 7, 10, tzinfo=UTC),
        )
        await pool.execute(
            "INSERT INTO sim_position(account_id,ticker,qty,avg_cost) "
            "VALUES($1,'AAPL',2,100),($1,'MSFT',1,100)", aid,
        )
        await pool.executemany(
            "INSERT INTO daily_prices(ticker,date,close) VALUES($1,$2,$3)",
            [('AAPL', day, 110), ('SPY', prior, 600), ('MSFT', date(2026, 7, 15), 200)],
        )
        await pool.execute(
            "INSERT INTO sim_equity_daily(account_id,as_of_date,portfolio_value,cash,unrealized_pnl,"
            "realized_pnl,benchmark_close) VALUES($1,$2,1100,800,0,0,600)", aid, prior,
        )
        await _run_paper_fill_locked(pool, day)
        equity = await pool.fetchrow(
            "SELECT * FROM sim_equity_daily WHERE account_id=$1 AND as_of_date=$2", aid, day,
        )
        assert equity['portfolio_value'] is None and equity['unrealized_pnl'] is None
        assert equity['valuation_quality'] == 'partial'
        assert equity['benchmark_close'] is None and equity['benchmark_close_at'] is None

        account = await _read_account(pool, uid, aid, now=as_of)
        assert account.portfolio_value is None and account.unrealized_pnl is None
        assert account.valuation_quality == 'partial' and account.reference_valuation is None
        positions = {pos.ticker: pos for pos in account.positions}
        assert positions['AAPL'].unrealized_pnl == 20
        assert positions['AAPL'].mark_at == '2026-07-14T20:00:00+00:00'
        assert positions['MSFT'].unrealized_pnl is None
        assert [(issue.ticker, issue.quality) for issue in account.valuation_issues] == [('MSFT', 'missing')]
        legacy, point = (await _read_equity_curve(pool, uid, aid)).series
        assert legacy.valuation_quality == 'legacy_unverified'
        assert legacy.portfolio_value is None and legacy.benchmark_index is None
        assert point.portfolio_value is None and point.benchmark_index is None
        inventory = Path('scripts/audit_paper_equity_history.sql').read_text()
        async with pool.acquire() as conn, conn.transaction(readonly=True):
            listing = await conn.fetch(inventory.split('BEGIN READ ONLY;')[1].split('ROLLBACK;')[0])
        assert [(row['as_of_date'], row['benchmark_evidence_gap']) for row in listing] == [
            (prior, 'no_recorded_provenance'),
        ]

        await pool.execute("INSERT INTO daily_prices(ticker,date,close) VALUES('MSFT',$1,105)", prior)
        account = await _read_account(pool, uid, aid, now=as_of)
        assert account.portfolio_value is None
        assert account.reference_valuation.portfolio_value == 1125
        assert account.reference_valuation.valued_at == '2026-07-13T20:00:00+00:00'
        await pool.execute("INSERT INTO daily_prices(ticker,date,close) VALUES('MSFT',$1,115)", day)
        await _run_paper_fill_locked(pool, day)
        point = (await _read_equity_curve(pool, uid, aid)).series[-1]
        assert point.portfolio_value == 1135 and point.benchmark_index is None
        assert (await _read_account(pool, uid, aid, now=as_of)).portfolio_value == point.portfolio_value


async def test_equity_waits_for_all_251_due_orders_but_allows_future_pending(applied_db):
    from datetime import UTC, datetime

    from alpha_agent.api.routes.cron_routes import _run_paper_fill_locked

    signal = date(2026, 7, 13)
    day = date(2026, 7, 14)
    async with asyncpg.create_pool(applied_db, min_size=1, max_size=2) as pool:
        rows = await pool.fetch(
            "INSERT INTO users(email) VALUES('backlog@test.example'),('future@test.example') RETURNING id",
        )
        due, future = [
            await pool.fetchval(
                "INSERT INTO sim_account(user_id,initial_cash,cash,created_at) "
                "VALUES($1,1000,1000,$2) RETURNING id", row['id'], datetime(2026, 7, 10, tzinfo=UTC),
            ) for row in rows
        ]
        await pool.execute(
            "INSERT INTO sim_order(account_id,ticker,side,order_type,qty,signal_date,limit_price) "
            "SELECT $1,'AAPL','buy','limit',1,$2,2 FROM generate_series(1,251)", due, signal,
        )
        await pool.execute(
            "INSERT INTO sim_order(account_id,ticker,side,order_type,qty,signal_date) "
            "VALUES($1,'AAPL','buy','market',1,$2)", future, day,
        )
        await pool.execute(
            "INSERT INTO daily_prices(ticker,date,close) VALUES('AAPL',$1,1),('SPY',$1,600)", day,
        )
        first = await _run_paper_fill_locked(pool, day)
        assert first['filled'] == 200
        assert await pool.fetchval("SELECT portfolio_value FROM sim_equity_daily WHERE account_id=$1", due) is None
        assert await pool.fetchval("SELECT portfolio_value FROM sim_equity_daily WHERE account_id=$1", future) == 1000

        second = await _run_paper_fill_locked(pool, day)
        assert second['filled'] == 51 and second['remaining_pending'] == 1
        row = await pool.fetchrow(
            "SELECT portfolio_value,benchmark_close,benchmark_close_at FROM sim_equity_daily WHERE account_id=$1", due,
        )
        assert row['portfolio_value'] == pytest.approx(1000 - 251 * 2.002 + 251)
        assert row['benchmark_close'] == 600
        assert row['benchmark_close_at'] == datetime(2026, 7, 14, 20, tzinfo=UTC)
