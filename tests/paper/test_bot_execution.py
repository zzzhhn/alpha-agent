"""Focused simulated ledger tests. No provider requests or database process."""
from __future__ import annotations

import copy
import json
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit
from uuid import uuid4

import pytest

from alpha_agent.paper import bot_execution as execution
from alpha_agent.paper.bot_models import BotConfig, BotDecision

NOW = datetime(2026, 11, 2, 15, 0, tzinfo=UTC)
RUN_ID = 'e244bba7-f974-4510-9831-cc273cf3f829'


class Ledger:
    """Small stateful SQL test double, including short-transaction rollback."""
    def __init__(self):
        self.account = {'id': 22, 'kind': 'bot', 'status': 'active', 'cash': 10000.0, 'reset_count': 0}
        self.config = BotConfig()
        self.run = {'id': RUN_ID, 'account_id': 22, 'status': 'running', 'config_version': 1,
                    'expires_at': NOW + timedelta(minutes=30), 'context': {'context_id': RUN_ID}}
        self.config_row = {'account_id': 22, 'config_version': 1, 'config': self.config.model_dump()}
        self.positions = {}
        self.orders = {}
        self.queries = []
        self.active_transactions = 0

    @asynccontextmanager
    async def acquire(self):
        yield self

    @asynccontextmanager
    async def transaction(self):
        snapshot = copy.deepcopy((self.account, self.positions, self.orders))
        self.active_transactions += 1
        try:
            yield
        except Exception:
            self.account, self.positions, self.orders = snapshot
            raise
        finally:
            self.active_transactions -= 1

    async def fetchrow(self, sql, *args):
        self.queries.append((sql, args))
        if 'FROM sim_account' in sql:
            return self.account if self.account['id'] == args[0] else None
        if 'FROM sim_bot_run' in sql:
            return self.run if args[:2] == (self.run['id'], self.account['id']) else None
        if 'FROM sim_bot_config' in sql:
            return self.config_row
        if 'FROM sim_position' in sql:
            return self.positions.get(args[2])
        if 'FROM sim_order' in sql:
            order = self.orders.get(args[0])
            if order is None or order['account_id'] != args[1]:
                return None
            if "status='pending'" in sql and order['status'] != 'pending':
                return None
            return dict(order)
        raise AssertionError(sql)

    async def fetch(self, sql, *args):
        self.queries.append((sql, args))
        if 'JOIN sim_account' in sql:
            return [dict(row) for row in self.orders.values() if row['status'] == 'pending'][:args[2]]
        if 'FROM sim_position' in sql:
            return [dict(row) for row in self.positions.values() if row['qty'] > 0]
        if 'WHERE bot_run_id=' in sql:
            return [dict(row) for row in self.orders.values() if row['bot_run_id'] == args[0]]
        if 'FROM sim_order' in sql:
            return [dict(row) for row in self.orders.values() if row['status'] == 'pending']
        raise AssertionError(sql)

    async def fetchval(self, sql, *args):
        self.queries.append((sql, args))
        if sql.startswith('INSERT INTO sim_order'):
            fields = ['account_id', 'ticker', 'side', 'qty', 'signal_date', 'cohort_id',
                      'reserved_notional', 'fee_bps', 'bot_run_id', 'action_id', 'instrument_id',
                      'execution_model', 'accepted_at', 'expires_at', 'reference_price', 'slippage_bps']
            order_id = len(self.orders) + 1
            self.orders[order_id] = dict(zip(fields, args)) | {
                'id': order_id, 'status': 'pending', 'cancel_requested_at': None,
            }
            return order_id
        if 'SUM(reserved_notional)' in sql:
            return sum(row['reserved_notional'] for row in self.orders.values()
                       if row['status'] == 'pending' and row['side'] == 'buy' and row['id'] != args[2])
        raise AssertionError(sql)

    async def execute(self, sql, *args):
        self.queries.append((sql, args))
        if sql.startswith('UPDATE sim_order SET cancel_requested_at='):
            order = self.orders[args[1]]
            order['cancel_requested_at'] = order['cancel_requested_at'] or args[0]
        elif "SET status='filled'" in sql:
            fields = ['fill_date', 'fill_price', 'transaction_cost', 'filled_at', 'reference_price', 'execution_evidence']
            self.orders[args[6]].update(dict(zip(fields, args[:6])) | {'status': 'filled', 'fail_reason': None})
        elif "SET status='failed',fail_reason='account_cohort_changed'" in sql:
            self.orders[args[0]].update(status='failed', fail_reason='account_cohort_changed')
        elif "SET status='failed'" in sql:
            self.orders[args[2]].update(status='failed', fail_reason=args[0], execution_evidence=args[1])
        elif 'UPDATE sim_order SET status=$1' in sql:
            self.orders[args[3]].update(status=args[0], fail_reason=args[1], execution_evidence=args[2])
        elif sql.startswith('INSERT INTO sim_position'):
            fields = ['account_id', 'cohort_id', 'ticker', 'qty', 'avg_cost', 'realized_pnl',
                      'instrument_id', 'mark_price', 'mark_at', 'price_quality']
            self.positions[args[2]] = dict(zip(fields, args))
        elif sql.startswith('UPDATE sim_account SET cash='):
            self.account['cash'] = args[0]
        else:
            raise AssertionError(sql)


def context():
    return {
        'context_id': RUN_ID, 'account': {'reset_count': 0}, 'evidence_ids': ['e1'],
        'instruments': [{'instrument_id': '1', 'ticker': 'AAPL'}, {'instrument_id': '2', 'ticker': 'MSFT'}],
        'quotes': {ticker: {'price': 100.0, 'as_of': (NOW - timedelta(minutes=1)).isoformat(),
                            'source': 'yfinance', 'quality': 'fresh', 'price_basis': 'raw_unadjusted'}
                   for ticker in ('AAPL', 'MSFT')},
    }


def decision(*actions):
    return BotDecision(context_id=RUN_ID, decision='rebalance', summary='Test simulated targets',
                       actions=list(actions) or [{'action_id': 'a1', 'instrument_id': '1', 'target_weight': 0.2}])


def bar(price=100.0, **values):
    return {'start': (NOW + timedelta(minutes=1)).isoformat(),
            'end': (NOW + timedelta(minutes=2)).isoformat(),
            'fetched_at': (NOW + timedelta(minutes=2)).isoformat(),
            'open': price, 'high': price, 'low': price, 'close': price,
            'source': 'test:raw', 'price_basis': 'raw_unadjusted',
            'dividends': 0.0, 'stock_splits': 0.0, 'corporate_actions_known': True} | values


async def submit(ledger, chosen=None, ctx=None, now=NOW):
    return await execution.submit_targets(ledger, dict(ledger.run), chosen or decision(),
                                          ctx or context(), ledger.config, now)


async def test_target_creates_market_order_and_reserves_fee_slippage_buffer():
    ledger = Ledger()
    results = await submit(ledger)
    order = ledger.orders[1]
    assert results[0]['status'] == 'accepted'
    assert order['qty'] == 20
    assert order['reserved_notional'] == pytest.approx(2000 * 1.0005 * 1.001 * 1.01)
    assert order['accepted_at'] == NOW
    assert order['execution_model'] == 'intraday_next_bar_v1'
    assert order['bot_run_id'] == RUN_ID
    assert ledger.account['cash'] == 10000


async def test_same_action_retry_returns_one_order():
    ledger = Ledger()
    await submit(ledger)
    results = await submit(ledger)
    assert results[0]['status'] == 'existing'
    assert len(ledger.orders) == 1


async def test_same_ticker_pending_different_action_is_deferred():
    ledger = Ledger()
    await submit(ledger)
    results = await submit(ledger, decision({'action_id': 'a2', 'instrument_id': '1', 'target_weight': 0.1}))
    assert results[0]['status'] == 'deferred'
    assert len(ledger.orders) == 1


@pytest.mark.parametrize('change,reason', [
    ({'quality': 'stale'}, 'fresh_raw_quote_required'),
    ({'price_basis': 'adjusted'}, 'fresh_raw_quote_required'),
    ({'as_of': (NOW - timedelta(minutes=6)).isoformat()}, 'stale_quote'),
    ({'as_of': (NOW + timedelta(seconds=1)).isoformat()}, 'stale_quote'),
    ({'price': float('nan')}, 'invalid_quote'),
])
async def test_no_daily_stale_future_or_invalid_quote_submitted(change, reason):
    ledger, ctx = Ledger(), context()
    ctx['quotes']['AAPL'].update(change)
    results = await submit(ledger, ctx=ctx)
    assert results[0] == {'action_id': 'a1', 'status': 'rejected', 'reason': reason}
    assert not ledger.orders


@pytest.mark.parametrize('kind,status,run_status,version,reason', [
    ('human', 'active', 'running', 1, 'active_bot_account_required'),
    ('bot', 'disabled', 'running', 1, 'active_bot_account_required'),
    ('bot', 'active', 'stopped', 1, 'active_run_required'),
    ('bot', 'active', 'running', 2, 'config_version_changed'),
])
async def test_transaction_revalidates_identity_state_and_config(kind, status, run_status, version, reason):
    ledger = Ledger()
    ledger.account.update(kind=kind, status=status)
    ledger.run['status'] = run_status
    ledger.config_row['config_version'] = version
    with pytest.raises(ValueError, match=reason):
        await submit(ledger)
    assert not ledger.orders


@pytest.mark.parametrize('mode', ['mismatched', 'expired', 'missing_deadline', 'null_token'])
async def test_lease_fences_stale_workers_before_any_submission(mode):
    ledger = Ledger()
    token = uuid4()
    ledger.run.update(lease_token=token, lease_until=NOW + timedelta(minutes=5))
    claimed = dict(ledger.run)
    if mode == 'mismatched':
        ledger.run['lease_token'] = uuid4()
    elif mode == 'expired':
        ledger.run['lease_until'] = NOW
    elif mode == 'missing_deadline':
        ledger.run['lease_until'] = None
    else:
        claimed['lease_token'] = None
    with pytest.raises(ValueError, match='run_lease_lost'):
        await execution.submit_targets(ledger, claimed, decision(), context(), ledger.config, NOW)
    assert not ledger.orders


async def test_current_unexpired_lease_accepts_string_or_uuid_identity():
    ledger = Ledger()
    token = uuid4()
    ledger.run.update(lease_token=token, lease_until=NOW + timedelta(minutes=5))
    claimed = dict(ledger.run) | {'lease_token': str(token)}
    results = await execution.submit_targets(ledger, claimed, decision(), context(), ledger.config, NOW)
    assert results[0]['status'] == 'accepted'


async def test_untouched_holding_counts_toward_total_capital():
    ledger = Ledger()
    ledger.account['cash'] = 100
    ledger.positions['MSFT'] = {'ticker': 'MSFT', 'qty': 100, 'avg_cost': 80.0, 'realized_pnl': 0}
    results = await submit(ledger)
    assert results[0]['reason'] == 'targets_exceed_total_capital'
    assert ledger.positions['MSFT']['qty'] == 100
    assert not ledger.orders


async def test_sells_submit_before_buys_without_spending_projected_proceeds():
    ledger = Ledger()
    ledger.account['cash'] = 0
    ledger.positions['AAPL'] = {'ticker': 'AAPL', 'qty': 100, 'avg_cost': 80.0, 'realized_pnl': 0}
    chosen = decision({'action_id': 'buy', 'instrument_id': '2', 'target_weight': 0.2},
                      {'action_id': 'sell', 'instrument_id': '1', 'target_weight': 0})
    results = await submit(ledger, chosen)
    assert [result['status'] for result in results] == ['deferred', 'accepted']
    assert ledger.orders[1]['side'] == 'sell'
    assert ledger.account['cash'] == 0


async def test_max_positions_and_weight_are_enforced():
    ledger = Ledger()
    results = await submit(ledger, decision({'action_id': 'a1', 'instrument_id': '1', 'target_weight': 0.3}))
    assert results[0]['reason'] == 'max_position_weight_exceeded'
    ledger.config = BotConfig(max_positions=1)
    ledger.config_row['config'] = ledger.config.model_dump()
    results = await submit(ledger, decision(
        {'action_id': 'a1', 'instrument_id': '1', 'target_weight': 0.2},
        {'action_id': 'a2', 'instrument_id': '2', 'target_weight': 0.2}))
    assert {result['reason'] for result in results} == {'max_positions_exceeded'}
    assert not ledger.orders


async def test_pending_sell_does_not_free_a_position_slot_before_settlement():
    ledger = Ledger()
    ledger.config = BotConfig(max_positions=1)
    ledger.config_row['config'] = ledger.config.model_dump()
    ledger.positions['AAPL'] = {'ticker': 'AAPL', 'qty': 10, 'avg_cost': 80.0, 'realized_pnl': 0}
    chosen = decision({'action_id': 'sell', 'instrument_id': '1', 'target_weight': 0},
                      {'action_id': 'buy', 'instrument_id': '2', 'target_weight': 0.2})
    results = await submit(ledger, chosen)
    assert [result['status'] for result in results] == ['accepted', 'deferred']
    assert results[1]['reason'] == 'awaiting_settled_position_slot'
    assert len(ledger.orders) == 1


async def test_buy_settlement_records_fee_weighted_cost_marks_and_is_idempotent(monkeypatch):
    ledger = Ledger()
    await submit(ledger)
    async def fetch(ticker, now):
        assert ledger.active_transactions == 0
        return [bar()]
    monkeypatch.setattr(execution, 'fetch_bars', fetch)
    first = await execution.settle_orders(ledger, 22, NOW + timedelta(minutes=3))
    assert first['filled'] == 1 and not first['errors']
    fee = 100.05 * 20 * 0.001
    assert ledger.account['cash'] == pytest.approx(10000 - 100.05 * 20 - fee)
    assert ledger.positions['AAPL']['avg_cost'] == pytest.approx(100.05 * 1.001)
    assert ledger.positions['AAPL']['mark_price'] == 100
    assert ledger.orders[1]['transaction_cost'] == pytest.approx(fee)
    cash = ledger.account['cash']
    second = await execution.settle_orders(ledger, 22, NOW + timedelta(minutes=3))
    assert second['filled'] == 0
    assert ledger.account['cash'] == cash


async def test_live_settlement_confirms_after_fetch_not_before_it(monkeypatch):
    ledger = Ledger()
    await submit(ledger)
    clock = {'now': NOW + timedelta(minutes=3)}

    class TestClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock['now']

    async def fetch(*args):
        assert ledger.active_transactions == 0
        clock['now'] = NOW + timedelta(minutes=3, seconds=20)
        return [bar(fetched_at=(NOW + timedelta(minutes=3, seconds=10)).isoformat())]

    monkeypatch.setattr(execution, 'datetime', TestClock)
    monkeypatch.setattr(execution, 'fetch_bars', fetch)
    result = await execution.settle_orders(ledger)
    assert result['filled'] == 1
    assert result['errors'] == []


async def test_sell_pnl_includes_fee_and_prior_realized_history(monkeypatch):
    ledger = Ledger()
    ledger.positions['AAPL'] = {'ticker': 'AAPL', 'qty': 10, 'avg_cost': 80.0, 'realized_pnl': 7.0}
    await submit(ledger, decision({'action_id': 'sell', 'instrument_id': '1', 'target_weight': 0}))
    async def fetch(*args):
        return [bar()]
    monkeypatch.setattr(execution, 'fetch_bars', fetch)
    result = await execution.settle_orders(ledger, now=NOW + timedelta(minutes=3))
    assert result['filled'] == 1
    assert ledger.positions['AAPL']['qty'] == 0
    assert ledger.positions['AAPL']['realized_pnl'] == pytest.approx(7 + (99.95 - 80) * 10 - 0.9995)
    assert ledger.account['cash'] == pytest.approx(10000 + 999.5 - 0.9995)


async def test_fill_price_gap_cannot_overdraw_cash_and_releases_reservation(monkeypatch):
    ledger = Ledger()
    await submit(ledger)
    async def fetch(*args):
        return [bar(price=1000)]
    monkeypatch.setattr(execution, 'fetch_bars', fetch)
    result = await execution.settle_orders(ledger, now=NOW + timedelta(minutes=3))
    assert result['failed'] == 1
    assert ledger.orders[1]['status'] == 'failed'
    assert ledger.account['cash'] == 10000
    assert not ledger.positions


async def test_late_reconciliation_does_not_label_an_old_bar_mark_fresh(monkeypatch):
    ledger = Ledger()
    await submit(ledger)
    async def fetch(*args):
        return [bar()]
    monkeypatch.setattr(execution, 'fetch_bars', fetch)
    result = await execution.settle_orders(ledger, now=NOW + timedelta(minutes=10))
    assert result['filled'] == 1
    assert ledger.positions['AAPL']['price_quality'] == 'stale'


@pytest.mark.parametrize('cancel_after_start,expected', [(False, 'cancelled'), (True, 'filled')])
async def test_cancellation_respects_eligible_bar_time(monkeypatch, cancel_after_start, expected):
    ledger = Ledger()
    await submit(ledger)
    cancel_time = NOW + timedelta(seconds=90 if cancel_after_start else 30)
    ctx = context()
    chosen = decision({'action_id': 'cancel', 'type': 'cancel_order', 'order_id': 1})
    await submit(ledger, chosen, ctx, cancel_time)
    assert ledger.orders[1]['status'] == 'pending'
    async def fetch(*args):
        return [bar()]
    monkeypatch.setattr(execution, 'fetch_bars', fetch)
    result = await execution.settle_orders(ledger, now=NOW + timedelta(minutes=3))
    assert result[expected] == 1
    assert ledger.orders[1]['status'] == expected


async def test_corporate_action_blocks_with_visible_reason(monkeypatch):
    ledger = Ledger()
    await submit(ledger)
    async def fetch(*args):
        return [bar(stock_splits=2)]
    monkeypatch.setattr(execution, 'fetch_bars', fetch)
    result = await execution.settle_orders(ledger, now=NOW + timedelta(minutes=3))
    assert result['pending'] == 1
    assert ledger.orders[1]['fail_reason'] == 'corporate_action_requires_reconciliation'
    assert ledger.account['cash'] == 10000


async def test_provider_errors_are_reported_once_per_ticker_without_locks(monkeypatch):
    ledger = Ledger()
    await submit(ledger)
    ledger.orders[2] = ledger.orders[1] | {'id': 2, 'action_id': 'other'}
    calls = []
    async def fetch(ticker, now):
        assert ledger.active_transactions == 0
        calls.append(ticker)
        raise RuntimeError('rate limited')
    monkeypatch.setattr(execution, 'fetch_bars', fetch)
    result = await execution.settle_orders(ledger, now=NOW + timedelta(minutes=3))
    assert calls == ['AAPL']
    assert result['pending'] == 2
    assert len(result['errors']) == 1
    assert 'rate limited' in result['errors'][0]['error']


async def test_cohort_change_never_writes_old_order_to_new_book(monkeypatch):
    ledger = Ledger()
    await submit(ledger)
    ledger.account['reset_count'] = 1
    async def fetch(*args):
        return [bar()]
    monkeypatch.setattr(execution, 'fetch_bars', fetch)
    result = await execution.settle_orders(ledger, now=NOW + timedelta(minutes=3))
    assert result['failed'] == 1
    assert ledger.account['cash'] == 10000
    assert not ledger.positions


@pytest.mark.skipif(not os.environ.get('ALPHA_PAPER_BOT_TEST_DSN'), reason='explicit local test DB only')
async def test_real_postgres_migrations_accept_fill_retry_preserve_human(monkeypatch):
    """Opt-in local-only SQL/invariant integration, retaining its audit rows."""
    import asyncpg

    from alpha_agent.paper.accounts import create_bot_account, resolve_account
    from alpha_agent.storage.migrations.runner import _discover, apply_migrations

    dsn = os.environ['ALPHA_PAPER_BOT_TEST_DSN']
    parsed = urlsplit(dsn)
    assert parsed.hostname in {'127.0.0.1', 'localhost', '::1'}
    assert parsed.path.removeprefix('/').startswith('alpha_paper_bot_test')
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute('CREATE TABLE IF NOT EXISTS schema_migrations '
                           '(version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ DEFAULT now())')
        applied = {row['version'] for row in await conn.fetch('SELECT version FROM schema_migrations')}
        for version, path in _discover():
            if int(version.split('__')[0][1:]) >= 49 or version in applied:
                continue
            async with conn.transaction():
                await conn.execute(path.read_text())
                await conn.execute('INSERT INTO schema_migrations(version) VALUES ($1)', version)
        user_id = await conn.fetchval('INSERT INTO users(email) VALUES($1) RETURNING id',
                                     f'bot-execution-{uuid4()}@example.test')
        human_id = await conn.fetchval(
            'INSERT INTO sim_account(user_id,initial_cash,cash,reset_count) VALUES($1,10000,8123,2) RETURNING id',
            user_id,
        )
        await conn.execute('INSERT INTO sim_position(account_id,ticker,qty,avg_cost,realized_pnl,cohort_id) '
                           "VALUES($1,'AAPL',3,100,12,2)", human_id)
        await conn.execute('INSERT INTO sim_equity_daily(account_id,as_of_date,portfolio_value,cash,'
                           "unrealized_pnl,realized_pnl,cohort_id) VALUES($1,'2026-10-30',8423,8123,0,12,2)", human_id)
        before = dict(await conn.fetchrow('SELECT * FROM sim_account WHERE id=$1', human_id))
        position_before = dict(await conn.fetchrow('SELECT * FROM sim_position WHERE account_id=$1', human_id))
        equity_before = dict(await conn.fetchrow('SELECT * FROM sim_equity_daily WHERE account_id=$1', human_id))
    finally:
        await conn.close()
    await apply_migrations(dsn)
    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=2)
    try:
        human = await resolve_account(pool, user_id)
        assert human['kind'] == 'human'
        assert {key: human[key] for key in before} == before
        position_after = dict(await pool.fetchrow('SELECT * FROM sim_position WHERE account_id=$1', human_id))
        equity_after = dict(await pool.fetchrow('SELECT * FROM sim_equity_daily WHERE account_id=$1', human_id))
        assert {key: position_after[key] for key in position_before} == position_before
        assert {key: equity_after[key] for key in equity_before} == equity_before
        bot = await create_bot_account(pool, user_id, 'SQL bot', 10000)
        assert bot['id'] != human_id
        assert (await create_bot_account(pool, user_id, 'Retry name', 99))['cash'] == 10000
        instrument_id = await pool.fetchval(
            "INSERT INTO sim_instrument(ticker) VALUES('AAPL') ON CONFLICT(ticker) "
            'DO UPDATE SET ticker=EXCLUDED.ticker RETURNING id')
        config = BotConfig()
        await pool.execute('INSERT INTO sim_bot_config(account_id,config) VALUES($1,$2::jsonb)',
                           bot['id'], config.model_dump_json())
        run_id = uuid4()
        ctx = context()
        ctx['context_id'] = str(run_id)
        ctx['instruments'] = [{'instrument_id': str(instrument_id), 'ticker': 'AAPL'}]
        await pool.execute(
            'INSERT INTO sim_bot_run(id,account_id,trigger,trading_session,status,expires_at,'
            "config_version,config_snapshot,context) VALUES($1,$2,'manual',$3,'running',$4,1,$5::jsonb,$6::jsonb)",
            run_id, bot['id'], NOW.date(), NOW + timedelta(minutes=30), config.model_dump_json(), json.dumps(ctx),
        )
        run = dict(await pool.fetchrow('SELECT * FROM sim_bot_run WHERE id=$1', run_id))
        run['id'] = str(run['id'])  # Exercise the runner's JSON-safe UUID contract.
        run.pop('lease_token')  # This direct ledger test is not a claimed worker.
        chosen = BotDecision(context_id=str(run_id), decision='rebalance', summary='SQL test', actions=[{
            'action_id': 'real1', 'instrument_id': str(instrument_id), 'target_weight': 0.2,
        }])
        submitted = await execution.submit_targets(pool, run, chosen, ctx, config, NOW)
        assert submitted[0]['status'] == 'accepted'
        assert (await execution.submit_targets(pool, run, chosen, ctx, config, NOW))[0]['status'] == 'existing'
        assert await pool.fetchval('SELECT count(*) FROM sim_order WHERE bot_run_id=$1', run_id) == 1
        with pytest.raises(asyncpg.UniqueViolationError):
            await pool.execute(
                'INSERT INTO sim_order(account_id,ticker,side,order_type,qty,signal_date,bot_run_id,action_id) '
                "VALUES($1,'AAPL','buy','market',1,$2,$3,'real1')", bot['id'], NOW.date(), run_id)
        async def fetch(*args):
            return [bar()]
        monkeypatch.setattr(execution, 'fetch_bars', fetch)
        settled = await execution.settle_orders(pool, bot['id'], NOW + timedelta(minutes=3))
        assert settled['filled'] == 1 and settled['errors'] == []
        saved_order = await pool.fetchrow('SELECT * FROM sim_order WHERE bot_run_id=$1', run_id)
        assert saved_order['status'] == 'filled'
        assert saved_order['fill_price'] == pytest.approx(100.05)
        assert saved_order['transaction_cost'] == pytest.approx(2.001)
        bot_after = dict(await pool.fetchrow('SELECT * FROM sim_account WHERE id=$1', bot['id']))
        assert bot_after['cash'] == pytest.approx(7996.999)
        assert (await execution.settle_orders(pool, bot['id'], NOW + timedelta(minutes=3)))['filled'] == 0
        assert await pool.fetchval('SELECT cash FROM sim_account WHERE id=$1', bot['id']) == bot_after['cash']
        human_after = await resolve_account(pool, user_id)
        assert {key: human_after[key] for key in before} == before
        assert await pool.fetchval('SELECT qty FROM sim_position WHERE account_id=$1', human_id) == 3
    finally:
        await pool.close()
