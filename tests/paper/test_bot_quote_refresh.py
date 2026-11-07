from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from alpha_agent.paper import bot_quote_refresh as refresh
from alpha_agent.paper import bot_valuation as valuation
from tests.paper.test_bot_valuation import bars


@pytest.mark.parametrize('instant,allowed', [
    ('2026-11-06T14:07:00+00:00', False),  # Winter pre-open.
    ('2026-11-06T14:37:00+00:00', True),
    ('2026-06-12T13:37:00+00:00', True),  # Summer open.
    ('2026-11-06T21:07:00+00:00', True),
    ('2026-11-06T21:37:00+00:00', False),
    ('2026-11-27T18:07:00+00:00', True),  # Shortened XNYS session.
    ('2026-11-27T18:37:00+00:00', False),
    ('2026-11-07T15:07:00+00:00', False),
])
def test_refresh_calendar_windows(instant, allowed):
    assert (refresh.refresh_slot(datetime.fromisoformat(instant)) is not None) == allowed


async def test_closed_market_and_low_storage_do_not_fetch_or_claim(monkeypatch):
    pool = MagicMock()
    capacity, claim, fetch = AsyncMock(return_value={'allow_writes': False}), AsyncMock(), AsyncMock()
    monkeypatch.setattr(refresh, 'read_capacity', capacity)
    monkeypatch.setattr(refresh, 'claim_refresh', claim)
    monkeypatch.setattr(refresh, 'refresh_marks', fetch)
    assert (await refresh.refresh_intraday_valuations(pool, datetime(2026,11,7,15,tzinfo=UTC)))['reason'] == 'outside_refresh_window'
    capacity.assert_not_awaited()
    assert (await refresh.refresh_intraday_valuations(pool, datetime(2026,11,6,15,tzinfo=UTC)))['reason'] == 'storage_headroom_low'
    claim.assert_not_awaited()
    fetch.assert_not_awaited()


async def test_global_budget_defers_whole_books_and_excludes_active_decisions(monkeypatch):
    now = datetime(2026,11,6,15,7,tzinfo=UTC)
    pool = MagicMock(fetch=AsyncMock(return_value=[{'id':1,'tickers':['A','B']}, {'id':2,'tickers':['C']}]), execute=AsyncMock())
    monkeypatch.setattr(refresh, 'read_capacity', AsyncMock(return_value={'allow_writes':True}))
    monkeypatch.setattr(refresh, 'claim_refresh', AsyncMock(return_value=1))
    monkeypatch.setattr(refresh, 'MAX_SYMBOLS', 3)
    async def fetch(pool, account_id, now, *, _cache):
        assert account_id == 1
        _cache.update({('2026-11-06',symbol):{} for symbol in ['SPY','A','B']})
        return {'valuation_quality':'fresh','errors':{}}
    mock = AsyncMock(side_effect=fetch)
    monkeypatch.setattr(refresh,'refresh_marks',mock)
    result = await refresh.refresh_intraday_valuations(pool,now)
    assert result['symbols_read'] == 3 and result['deferred_accounts'] == 1
    assert mock.await_count == 1
    assert "r.status IN ('queued','running')" in pool.fetch.call_args.args[0]


async def test_real_database_keeps_last_good_snapshot_and_deduplicates_ticks(applied_db, monkeypatch):
    from alpha_agent.storage.postgres import close_pool, get_pool
    from alpha_agent.api.routes import paper
    pool = await get_pool(applied_db)
    now = datetime(2026,11,6,15,7,tzinfo=UTC)
    try:
        user = await pool.fetchval("INSERT INTO users(email) VALUES('valuation-test@example.invalid') RETURNING id")
        account = dict(await pool.fetchrow(
            "INSERT INTO sim_account(user_id,kind,name,initial_cash,cash,created_at) VALUES($1,'bot','test',1000,1000,$2) RETURNING *",
            user, now - timedelta(days=1)))
        await pool.execute("INSERT INTO sim_position(account_id,ticker,qty,avg_cost,cohort_id) VALUES($1,'AAPL',2,90,0)",account['id'])
        fetch = AsyncMock(return_value=bars(now))
        monkeypatch.setattr(valuation,'fetch_bars',fetch)
        result = await refresh.refresh_intraday_valuations(pool,now)
        assert result['updated_accounts'] == 1 and fetch.await_count == 2
        assert (await refresh.refresh_intraday_valuations(pool,now+timedelta(minutes=1)))['reason'] == 'already_checked'
        assert fetch.await_count == 2
        fetch.return_value = []
        await refresh.refresh_intraday_valuations(pool,now+timedelta(minutes=30))
        snapshot = await valuation.last_valid_valuation(pool,account,now+timedelta(minutes=30))
        assert snapshot['portfolio_value'] == 1200 and snapshot['valued_at'] == now.isoformat()
        assert snapshot['total_return_pct'] == pytest.approx(20)
        assert await pool.fetchval('SELECT count(*) FROM sim_equity_daily') == 1
        assert await pool.fetchval("SELECT count(*) FROM cron_runs WHERE cron_name=$1",refresh.JOB) == 1
        assert await pool.fetchval('SELECT count(*) FROM sim_bot_run') == 0
        assert await pool.fetchval('SELECT count(*) FROM sim_order') == 0
        current = await paper._read_account(pool,user,account['id'])
        assert current.portfolio_value is None  # Stale prices remain invalid for current valuation.
        assert current.last_valid_valuation.portfolio_value == 1200
        assert await valuation.last_valid_valuation(pool,{**account,'reset_count':1},now+timedelta(minutes=30)) is None
    finally:
        await close_pool()
