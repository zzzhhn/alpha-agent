"""Integration test for the paper_fill cron against a real test DB."""
import pytest
import asyncpg
from datetime import date, timedelta


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
        fill_date = date(2026, 7, 11)
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
            signal_date + timedelta(days=1),
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
            "INSERT INTO sim_account (user_id, cash) VALUES ($1, 1000.0) RETURNING id",
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
            date(2026, 7, 11),
        )

        from alpha_agent.api.routes.cron_routes import _write_paper_equity_snapshots

        as_of = date(2026, 7, 12)
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
