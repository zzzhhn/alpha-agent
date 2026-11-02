"""Bounded valuation and API/cron isolation without a database process/network."""
import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from alpha_agent.paper import bot_valuation as valuation

NOW = datetime(2026, 11, 2, 15, 0, tzinfo=UTC)


def position(ticker='AAPL', **overrides):
    return {'account_id': 22, 'cohort_id': 0, 'ticker': ticker, 'qty': 2, 'avg_cost': 90,
            'realized_pnl': 4, 'mark_price': None, 'mark_at': None, 'price_quality': None} | overrides


def bars(now=NOW, **overrides):
    return [{'start': (now - timedelta(minutes=1)).isoformat(), 'end': now.isoformat(),
             'open': 100, 'high': 101, 'low': 99, 'close': 100, 'volume': 20,
             'source': 'test:raw', 'fetched_at': now.isoformat(),
             'price_basis': 'raw_unadjusted', 'corporate_actions_known': True,
             'corporate_actions': [], 'dividends': 0, 'stock_splits': 0} | overrides]


class Book:
    def __init__(self, positions=None):
        self.account = {'id': 22, 'kind': 'bot', 'cash': 1000, 'reset_count': 0}
        self.positions = [position()] if positions is None else positions
        self.depth = 0
        self.snapshot = None
        self.queries = []

    @asynccontextmanager
    async def acquire(self):
        yield self

    @asynccontextmanager
    async def transaction(self):
        self.depth += 1
        try:
            yield
        finally:
            self.depth -= 1

    async def fetchrow(self, sql, *args):
        self.queries.append(sql)
        assert "kind='bot'" in sql
        return dict(self.account)

    async def fetch(self, sql, *args):
        self.queries.append(sql)
        if 'FROM sim_account' in sql:
            return [{'id': 22}]
        assert 'FROM sim_position' in sql
        return [dict(row) for row in self.positions]

    async def execute(self, sql, *args):
        self.queries.append(sql)
        assert self.depth == 1
        if sql.startswith('UPDATE sim_position'):
            row = next(row for row in self.positions if row['ticker'] == args[5])
            row.update(mark_price=args[0], mark_at=args[1], price_quality=args[2])
        else:
            assert sql.startswith('INSERT INTO sim_equity_daily')
            self.snapshot = args


async def test_refresh_uses_raw_marks_and_cash_reread_without_network_locks(monkeypatch):
    book, calls = Book(), []

    async def fetch(ticker, now=None):
        assert book.depth == 0
        calls.append(ticker)
        book.account['cash'] = 800  # A concurrent fill happened during provider I/O.
        return bars()

    monkeypatch.setattr(valuation, 'fetch_bars', fetch)
    result = await valuation.refresh_marks(book, 22, NOW)
    assert calls == ['SPY', 'AAPL']
    assert result['portfolio_value'] == 1000
    assert result['unrealized_pnl'] == 20
    assert result['benchmark_close'] == 100
    assert result['valuation_quality'] == 'fresh'
    assert book.snapshot[2].isoformat() == '2026-11-02'
    assert book.snapshot[4] == 800
    assert all('daily_prices' not in sql for sql in book.queries)


async def test_new_premarket_account_never_backdates_nav(monkeypatch):
    book = Book()
    book.account['created_at'] = datetime(2026, 11, 2, 12, tzinfo=UTC)
    monkeypatch.setattr(valuation, 'fetch_bars', AsyncMock(return_value=[]))
    result = await valuation.refresh_marks(book, 22, datetime(2026, 11, 2, 12, 10, tzinfo=UTC))
    assert result['sample_written'] is False
    assert result['benchmark_quality'] == 'before_account_creation'
    assert book.snapshot is None


async def test_missing_mark_is_null_nav_not_cost_or_cash_proxy(monkeypatch):
    book = Book()
    monkeypatch.setattr(valuation, 'fetch_bars', AsyncMock(return_value=[]))
    result = await valuation.refresh_marks(book, 22, NOW)
    assert result['portfolio_value'] is None and result['unrealized_pnl'] is None
    assert result['benchmark_close'] is None
    assert result['valuation_quality'] == 'partial'
    assert book.snapshot[3] is None and book.snapshot[5] is None
    assert book.snapshot[6] == 4  # Realized accounting survives missing marks.


async def test_cash_only_gets_daily_sample_without_any_orders(monkeypatch):
    book = Book([])
    monkeypatch.setattr(valuation, 'fetch_bars', AsyncMock(return_value=[]))
    result = await valuation.refresh_marks(book, 22, NOW)
    assert result['portfolio_value'] == 1000 and result['valuation_quality'] == 'cash_only'
    assert book.snapshot is not None and book.snapshot[7] is None
    assert all('sim_order' not in sql for sql in book.queries)


async def test_corporate_event_freezes_only_affected_position_and_persists(monkeypatch):
    book = Book()
    monkeypatch.setattr(valuation, 'fetch_bars', AsyncMock(return_value=bars(stock_splits=2)))
    result = await valuation.refresh_marks(book, 22, NOW)
    assert result['portfolio_value'] is None
    assert result['valuation_quality'] == 'corporate_action_blocked'
    monkeypatch.setattr(valuation, 'fetch_bars', AsyncMock(return_value=bars()))
    result = await valuation.refresh_marks(book, 22, NOW)
    assert result['valuation_quality'] == 'corporate_action_blocked'


async def test_symbol_budget_and_round_cache_are_bounded(monkeypatch):
    book = Book([position(f'T{i:02}') for i in range(24)])
    mock = AsyncMock(return_value=bars())
    monkeypatch.setattr(valuation, 'fetch_bars', mock)
    cache = {}
    result = await valuation.refresh_marks(book, 22, NOW, _cache=cache)
    assert mock.await_count == valuation.MAX_SYMBOLS
    assert len(cache) == valuation.MAX_SYMBOLS and result['portfolio_value'] is None
    assert len(result['errors']) == 4
    await valuation.refresh_marks(book, 22, NOW, _cache=cache)
    assert mock.await_count == valuation.MAX_SYMBOLS


async def test_real_clock_uses_post_fetch_instant_not_request_start(monkeypatch):
    book = Book()

    class Clock(datetime):
        count = 0

        @classmethod
        def now(cls, tz=None):
            cls.count += 1
            return NOW if cls.count == 1 else NOW + timedelta(seconds=3)

    monkeypatch.setattr(valuation, 'datetime', Clock)
    monkeypatch.setattr(valuation, 'fetch_bars', AsyncMock(return_value=bars(
        fetched_at=(NOW + timedelta(seconds=2)).isoformat(),
    )))
    result = await valuation.refresh_marks(book, 22)
    assert result['portfolio_value'] == 1200
    assert result['benchmark_close'] == 100


async def test_explicit_asof_does_not_accept_evidence_from_future(monkeypatch):
    book = Book()
    monkeypatch.setattr(valuation, 'fetch_bars', AsyncMock(return_value=bars(
        fetched_at=(NOW + timedelta(seconds=2)).isoformat(),
    )))
    result = await valuation.refresh_marks(book, 22, NOW)
    assert result['portfolio_value'] is None


async def test_provider_concurrency_is_at_most_two(monkeypatch):
    book = Book([position('AAPL'), position('MSFT'), position('NVDA')])
    active, maximum = 0, 0

    async def fetch(ticker, now=None):
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        await asyncio.sleep(0)
        active -= 1
        return bars()

    monkeypatch.setattr(valuation, 'fetch_bars', fetch)
    await valuation.refresh_marks(book, 22, NOW)
    assert maximum == 2


async def test_provider_budget_exhaustion_writes_missing_sample(monkeypatch):
    book = Book()

    async def fetch(ticker, now=None):
        await asyncio.sleep(1)
        return bars()

    monkeypatch.setattr(valuation, 'fetch_bars', fetch)
    monkeypatch.setattr(valuation, 'FETCH_BUDGET_SECONDS', 0.001)
    result = await valuation.refresh_marks(book, 22, NOW)
    assert result['portfolio_value'] is None and book.snapshot is not None
    assert result['errors'] == {'SPY': 'fetch_budget_exceeded', 'AAPL': 'fetch_budget_exceeded'}


async def test_daily_hook_runs_without_orders_and_shares_bounded_cache(monkeypatch):
    book = Book([])
    monkeypatch.setattr(valuation, 'fetch_bars', AsyncMock(return_value=bars()))
    result = await valuation.refresh_daily_valuations(book, NOW)
    assert result['accounts'][0]['valuation_quality'] == 'cash_only'
    assert result['symbols_read'] == 1 and result['symbol_limit'] == 21
    assert not result['has_more_accounts']


async def test_provider_failure_is_data_quality_not_false_zero(monkeypatch):
    book = Book()
    monkeypatch.setattr(valuation, 'fetch_bars', AsyncMock(side_effect=TimeoutError('private detail')))
    result = await valuation.refresh_marks(book, 22, NOW)
    assert result['portfolio_value'] is None
    assert result['errors'] == {'SPY': 'TimeoutError', 'AAPL': 'TimeoutError'}
    assert 'private detail' not in str(result)


async def test_failed_or_slower_refresh_does_not_erase_newer_persisted_mark(monkeypatch):
    book = Book([position(mark_price=110, mark_at=NOW, price_quality='fresh')])
    monkeypatch.setattr(valuation, 'fetch_bars', AsyncMock(return_value=[]))
    result = await valuation.refresh_marks(book, 22, NOW)
    assert result['portfolio_value'] == 1220
    assert book.positions[0]['mark_price'] == 110


def test_ny_date_and_exact_raw_close_not_utc_calendar_or_early_bar():
    now = datetime(2026, 11, 3, 1, 0, tzinfo=UTC)
    assert valuation.valuation_session(now)['session_date'] == '2026-11-02'
    last_close = datetime(2026, 11, 2, 21, 0, tzinfo=UTC)
    row = position(mark_price=100, mark_at=last_close, price_quality='fresh')
    assert valuation.summarize_marks([row], 1000, now)['valuation_quality'] == 'session_close'
    row['mark_at'] = last_close - timedelta(minutes=1)
    result = valuation.summarize_marks([row], 1000, now)
    assert result['portfolio_value'] is None and result['marks']['AAPL']['quality'] == 'stale'


def test_stale_fresh_future_invalid_and_weekend_marks():
    row = position(mark_price=100, mark_at=NOW - timedelta(minutes=6), price_quality='fresh')
    assert valuation.effective_mark(row, NOW)['quality'] == 'stale'
    row['mark_at'] = NOW + timedelta(minutes=1)
    assert valuation.effective_mark(row, NOW)['price'] is None
    row.update(mark_at=NOW, mark_price=float('nan'))
    assert valuation.effective_mark(row, NOW)['price'] is None
    saturday = datetime(2026, 11, 7, 12, 0, tzinfo=UTC)
    assert valuation.valuation_session(saturday)['session_date'] == '2026-11-06'


async def test_bot_api_never_reads_adjusted_daily_prices_and_exposes_nulls(monkeypatch):
    from alpha_agent.api.routes import paper

    pool = MagicMock()
    pool.fetch = AsyncMock(return_value=[position()])
    pool.fetchval = AsyncMock(return_value=0)
    monkeypatch.setattr(paper, 'resolve_account', AsyncMock(return_value={
        'id': 22, 'kind': 'bot', 'cash': 1000, 'initial_cash': 1000, 'reset_count': 0,
    }))
    closes = AsyncMock()
    monkeypatch.setattr(paper, '_current_closes', closes)
    result = await paper._read_account(pool, 7, 22)
    closes.assert_not_awaited()
    assert result.portfolio_value is None and result.total_return_pct is None
    assert result.unrealized_pnl is None and result.positions[0].unrealized_pnl is None
    assert result.positions[0].current_price is None
    assert result.positions[0].price_quality == 'missing'


async def test_bot_curve_missing_benchmark_does_not_fake_one_hundred(monkeypatch):
    from alpha_agent.api.routes import paper

    monkeypatch.setattr(paper, 'resolve_account', AsyncMock(return_value={'id': 22, 'kind': 'bot', 'reset_count': 0}))
    pool = MagicMock()
    pool.fetch = AsyncMock(return_value=[{
        'as_of_date': NOW.date(), 'portfolio_value': None, 'benchmark_close': None,
        'valuation_quality': 'partial', 'valued_at': NOW,
    }])
    result = await paper._read_equity_curve(pool, 7, 22)
    assert result.series[0].portfolio_value is None
    assert result.series[0].benchmark_index is None


def test_order_evidence_is_small_whitelisted_and_parseable():
    from alpha_agent.api.routes.paper import _small_execution_evidence

    result = _small_execution_evidence({'status': 'filled', 'secret': 'drop', 'bar': {
        'start': 't', 'close': 100, 'huge': list(range(1000)),
    }})
    assert result == {'status': 'filled', 'bar': {'start': 't', 'close': 100}}


async def test_empty_human_order_batch_still_writes_equity(monkeypatch):
    from alpha_agent.api.routes import cron_routes

    book = Book([])
    book.fetch = AsyncMock(return_value=[])
    book.fetchval = AsyncMock(return_value=0)
    snapshot = AsyncMock()
    monkeypatch.setattr(cron_routes, '_write_paper_equity_snapshots', snapshot)
    result = await cron_routes._run_paper_fill_locked(book, NOW.date())
    assert result['filled'] == 0
    snapshot.assert_awaited_once_with(book, NOW.date())
    sql = book.fetch.call_args.args[0]
    assert "sa.kind='human'" in sql and "so.execution_model='daily_close_v1'" in sql


async def test_legacy_equity_aggregate_is_human_only():
    from alpha_agent.api.routes import cron_routes

    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=[])
    await cron_routes._write_paper_equity_snapshots(conn, NOW.date())
    sql = conn.fetch.call_args.args[0]
    assert sql.count("sa.kind='human'") == 3


def test_daily_valuation_is_wired_after_human_fill_lease():
    source = Path(__file__).parents[2] / 'alpha_agent/api/routes/cron_routes.py'
    text = source.read_text()
    assert "result = await _run_paper_fill(dsn)" in text
    assert "result['bot_valuation'] = await refresh_daily_valuations(await get_pool(dsn))" in text
