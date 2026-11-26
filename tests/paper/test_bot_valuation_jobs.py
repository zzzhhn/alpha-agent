"""Synthetic daily valuation jobs on isolated PostgreSQL."""
import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import asyncpg

from alpha_agent.paper import bot_valuation as valuation
from tests.paper.test_bot_valuation import bars

CLOSE = datetime(2026, 11, 2, 21, tzinfo=UTC)
ROUND = CLOSE + timedelta(hours=4)


async def seed_account(pool, index, *, status='active', tickers=()):
    uid = await pool.fetchval("INSERT INTO users(email) VALUES($1) RETURNING id", f"valuation-{index}@test.example")
    account_id = await pool.fetchval(
        "INSERT INTO sim_account(user_id,kind,cash,initial_cash,status,created_at) "
        "VALUES($1,'bot',1000,1000,$2,$3) RETURNING id", uid, status, CLOSE - timedelta(days=1),
    )
    await pool.executemany(
        "INSERT INTO sim_position(account_id,ticker,qty,avg_cost) VALUES($1,$2,1,90)",
        [(account_id, ticker) for ticker in tickers],
    )
    return account_id


async def test_daily_bot_valuations_resume_after_first_ten_and_recover_abandoned_claim(applied_db, monkeypatch):
    calls = []

    async def fetch(ticker, now):
        calls.append(ticker)
        return bars(now)

    monkeypatch.setattr(valuation, 'fetch_bars', fetch)
    async with asyncpg.create_pool(applied_db, min_size=1, max_size=1) as pool:
        eligible = [await seed_account(pool, i, status='paused' if i == 11 else 'active') for i in range(12)]
        archived = await seed_account(pool, 12, status='disabled')
        first = await valuation.refresh_daily_valuations(pool, ROUND)
        assert [row['account_id'] for row in first['accounts']] == eligible[:10]
        assert first['has_more_accounts'] and calls == ['SPY']
        second = await valuation.refresh_daily_valuations(pool, ROUND + timedelta(minutes=15))
        assert [row['account_id'] for row in second['accounts']] == eligible[10:]
        assert not second['has_more_accounts'] and calls == ['SPY', 'SPY']
        assert (await valuation.refresh_daily_valuations(pool, ROUND))['accounts'] == []
        assert calls == ['SPY', 'SPY']

        snapshots = await pool.fetch(
            "SELECT account_id,valuation_quality FROM sim_equity_daily ORDER BY account_id",
        )
        assert [tuple(row) for row in snapshots] == [(aid, 'cash_only') for aid in eligible]
        archived_job = await pool.fetchrow(
            "SELECT status,reason FROM sim_bot_valuation_job WHERE account_id=$1", archived,
        )
        assert tuple(archived_job) == ('skipped', 'account_disabled')

        # Simulate a process dying after taking a claim, before persisting a mark.
        await pool.execute(
            "UPDATE sim_bot_valuation_job SET status='running',claim_token=$1,lease_until=$2 "
            "WHERE account_id=$3", uuid4(), ROUND + timedelta(minutes=1), eligible[-1],
        )
        assert (await valuation.refresh_daily_valuations(pool, ROUND))['accounts'] == []
        recovered = await valuation.refresh_daily_valuations(pool, ROUND + timedelta(minutes=15))
        assert [row['account_id'] for row in recovered['accounts']] == [eligible[-1]]
        assert await pool.fetchval(
            "SELECT attempts FROM sim_bot_valuation_job WHERE account_id=$1", eligible[-1],
        ) == 2


async def test_daily_bot_symbol_budget_defers_whole_book_and_quote_gap_is_partial(applied_db, monkeypatch):
    calls = []

    async def fetch(ticker, now):
        calls.append(ticker)
        return [] if ticker == 'EE' else bars(now)

    monkeypatch.setattr(valuation, 'MAX_SYMBOLS', 3)
    monkeypatch.setattr(valuation, 'fetch_bars', fetch)
    async with asyncpg.create_pool(applied_db, min_size=1, max_size=1) as pool:
        first = await seed_account(pool, 1, tickers=('AA', 'BB'))
        second = await seed_account(pool, 2, tickers=('CC', 'DD'))
        third = await seed_account(pool, 3, tickers=('EE',))
        outcome = await valuation.refresh_daily_valuations(pool, ROUND)
        assert [row['valuation_quality'] for row in outcome['accounts']] == ['session_close', None, None]
        assert [row['status'] for row in outcome['accounts']] == ['completed', 'deferred', 'deferred']
        assert [row['reason'] for row in outcome['accounts'][1:]] == ['symbol_budget_exceeded'] * 2
        assert set(calls) == {'SPY', 'AA', 'BB'}
        assert (await pool.fetch("SELECT account_id FROM sim_equity_daily"))[0]['account_id'] == first

        outcome = await valuation.refresh_daily_valuations(pool, ROUND + timedelta(minutes=15))
        assert [row['account_id'] for row in outcome['accounts']] == [second, third]
        assert outcome['accounts'][0]['valuation_quality'] == 'session_close'
        assert outcome['accounts'][1]['status'] == 'deferred'
        assert set(calls[:6]) == {'SPY', 'AA', 'BB', 'CC', 'DD'}

        outcome = await valuation.refresh_daily_valuations(pool, ROUND + timedelta(minutes=30))
        assert not outcome['has_more_accounts']
        assert outcome['accounts'][0]['status'] == 'completed'
        assert outcome['accounts'][0]['valuation_quality'] == 'partial'
        assert await pool.fetchval(
            "SELECT valuation_quality FROM sim_equity_daily WHERE account_id=$1", third,
        ) == 'partial'


async def test_concurrent_daily_trigger_cannot_publish_a_superseded_claim(applied_db, monkeypatch):
    first_fetch_started, release_first = asyncio.Event(), asyncio.Event()
    fetches = 0

    async def fetch(ticker, now):
        nonlocal fetches
        fetches += 1
        if fetches == 1:
            first_fetch_started.set()
            await release_first.wait()
            return bars(now, close=95)
        return bars(now, close=105)

    monkeypatch.setattr(valuation, 'fetch_bars', fetch)
    async with asyncpg.create_pool(applied_db, min_size=1, max_size=1) as pool:
        account_id = await seed_account(pool, 1)
        first = asyncio.create_task(valuation.refresh_daily_valuations(pool, ROUND))
        try:
            await asyncio.wait_for(first_fetch_started.wait(), timeout=2)
            duplicate = await valuation.refresh_daily_valuations(pool, ROUND + timedelta(minutes=1))
            assert duplicate['accounts'] == [] and duplicate['has_more_accounts']
            assert fetches == 1
            recovered = await valuation.refresh_daily_valuations(pool, ROUND + timedelta(minutes=6))
            assert recovered['accounts'][0]['status'] == 'completed'
        finally:
            release_first.set()
            stale = await first

        assert stale['accounts'][0]['status'] == 'superseded'
        assert fetches == 2
        assert await pool.fetchval(
            "SELECT benchmark_close FROM sim_equity_daily WHERE account_id=$1", account_id,
        ) == 105
        job = await pool.fetchrow(
            "SELECT status,attempts FROM sim_bot_valuation_job WHERE account_id=$1", account_id,
        )
        assert tuple(job) == ('completed', 2)


async def test_never_attempted_books_are_not_starved_by_ten_permanent_deferrals(applied_db, monkeypatch):
    calls = []

    async def fetch(ticker, now):
        calls.append(ticker)
        return bars(now)

    monkeypatch.setattr(valuation, 'MAX_SYMBOLS', 1)
    monkeypatch.setattr(valuation, 'fetch_bars', fetch)
    async with asyncpg.create_pool(applied_db, min_size=1, max_size=1) as pool:
        deferred = [await seed_account(pool, i, tickers=('AA',)) for i in range(10)]
        cash_only = [await seed_account(pool, i) for i in range(10, 12)]
        first = await valuation.refresh_daily_valuations(pool, ROUND)
        assert [(row['account_id'], row['status']) for row in first['accounts']] == [
            (aid, 'deferred') for aid in deferred
        ]
        assert calls == []

        second = await valuation.refresh_daily_valuations(pool, ROUND + timedelta(minutes=15))
        assert [(row['account_id'], row['status']) for row in second['accounts'][:2]] == [
            (aid, 'completed') for aid in cash_only
        ]
        assert [row['account_id'] for row in second['accounts'][2:]] == deferred[:8]
        assert calls == ['SPY']
        assert [row['account_id'] for row in await pool.fetch(
            "SELECT account_id FROM sim_equity_daily ORDER BY account_id",
        )] == cash_only

        third = await valuation.refresh_daily_valuations(pool, ROUND + timedelta(minutes=30), limit=2)
        assert [(row['account_id'], row['status']) for row in third['accounts']] == [
            (aid, 'deferred') for aid in deferred[-2:]
        ]
