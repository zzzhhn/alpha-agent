from datetime import timedelta
from decimal import Decimal

import asyncpg
import pytest

from alpha_agent.paper import event_shadow_policy as p
from alpha_agent.paper.event_shadow import _carry, read_event_shadow, run_event_shadow_cycle
from alpha_agent.paper.market_clock import as_utc


def instant(value):
    return as_utc('2026-11-23T' + value + 'Z')


def bar(ticker, start, *, close=100, volume=50_000, received=None):
    start = as_utc(start)
    end = start + timedelta(minutes=1)
    return dict(ticker=ticker, start=start, end=end, fetched_at=received or end + timedelta(seconds=2),
                close=close, volume=volume, source='test_raw_minutes', price_basis='raw_unadjusted',
                corporate_actions_known=True, corporate_actions=[])


def loan(**changes):
    base = dict(ticker='ABC', source='test_verified_lend', status='easy_to_borrow', evidence_id='receipt-1',
                loan_id='xyz', observed_at=instant('14:33:00'), valid_until=instant('21:00:00'),
                available_shares=100, annual_rate='1.00')
    return base | changes


def test_rule_is_deterministic_and_abstains_on_ambiguous_or_wrong_object():
    def signal(headline):
        return p.direction_for(dict(source='investor_relations', status='observed', title=headline))[0]

    assert signal('ABC Reports Results and Raises FY 2026 Revenue Guidance') == 'long'
    assert signal('ABC Lowers Full-Year Earnings Outlook') == 'short'
    assert signal('ABC raises dividend and reaffirms fiscal year outlook') is None
    assert signal('ABC raises FY 2026 sales guidance but cuts profit outlook') is None
    assert signal('CEO returns; ABC to discuss financial outlook') is None
    assert signal('ABC may lower full-year financial guidance') is None


def test_quotes_are_pit_regular_raw_and_conflicts_fail_closed():
    now = instant('14:34:30')
    earliest = bar('ABC', instant('14:31:00'))
    newer = dict(earliest, close=89, fetched_at=instant('14:33:00'))
    premarket = bar('ABC', instant('14:29:00'))
    future = bar('ABC', instant('14:34:00'))
    old = bar('ABC', instant('14:30:00'), received=instant('14:29:00'))
    conflicting = bar('ABC', instant('14:32:00'))
    seen = p.eligible_bars([newer, old, conflicting, earliest, premarket, future, dict(conflicting, close=101)],
                           now, 'ABC')
    assert [item['close'] for item in seen] == [Decimal(100)]
    assert not p.eligible_bars([earliest], instant('21:00:00'), 'ABC')


def test_risk_is_based_on_current_nav_and_caps_short_notional_and_volume():
    assert p.risk_capacity('short', Decimal(80_000), Decimal(0), Decimal(0)) == 4_000
    assert p.risk_capacity('short', Decimal(80_000), Decimal(16_000), Decimal(16_000)) == 0
    assert p.risk_capacity('long', Decimal(80_000), Decimal(25_000), Decimal(0)) == 0
    current = p.eligible_bars([bar('ABC', instant('14:34:00'), volume=300)], instant('14:35:30'), 'ABC')[0]
    chosen = p.entry_loan([loan(available_shares=2)], 'ABC', current['end'], instant('14:35:30'))
    fill = p.open_trade('short', current, Decimal(100_000), Decimal(4_000), chosen)
    assert fill['qty'] == 2
    assert fill['held'] == Decimal('299.70')
    assert fill['free_delta'] == Decimal('-100.10')
    assert p.entry_loan([loan(annual_rate=None)], 'ABC', current['end'], instant('14:35:30')) is None


def test_no_carry_without_each_session_and_short_owes_dividend():
    opening = instant('20:50:00')
    ending = as_utc('2026-11-24T14:40:00Z')
    trial = {'entry_at': opening, 'entry_price': Decimal(100), 'qty': 10, 'direction': 'short'}
    terms = {'valid_until': ending + timedelta(hours=2), 'annual_rate': '0.60'}
    receipts = {'borrow_terms': terms, 'actions': {'2026-11-23': {'dividend_per_share': '0.75', 'split': False}}}
    assert _carry(trial, receipts, {'end': ending}) == 'awaiting_corporate_action_evidence'
    receipts['actions']['2026-11-24'] = {'dividend_per_share': '1.25', 'split': False}
    interest, dividend = _carry(trial, receipts, {'end': ending})
    assert interest > 0 and dividend == Decimal('-12.50')
    receipts['actions']['2026-11-24']['split'] = True
    assert _carry(trial, receipts, {'end': ending}) == 'split_requires_reconciliation'


async def official(pool, *, key, headline, seen, published, source='investor_relations', ticker='ABC',
                   quality='source_timestamp', status='observed'):
    return await pool.fetchval(
        'INSERT INTO official_event_watch(ticker,source,source_key,content_hash,title,url,first_seen_at,published_at,'
        'published_at_quality,kind,status) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11) RETURNING id',
        ticker, source, key, headline, headline, 'https://investor.example/' + key, seen, published,
        quality, 'guidance', status,
    )


@pytest.mark.asyncio
async def test_forward_books_premarket_old_release_duplicates_and_short_hold(applied_db):
    pool = await asyncpg.create_pool(applied_db, min_size=1, max_size=2)
    try:
        assert (await read_event_shadow(pool))['status'] == 'not_activated'
        seen = instant('14:20:00')
        news = 'ABC Lowers Full-Year Earnings Outlook'
        await official(pool, key='preactivation', headline=news, published=seen - timedelta(minutes=5),
                       seen=seen - timedelta(minutes=4))
        await run_event_shadow_cycle(pool, now=instant('14:18:00'), quotes=[])
        await official(pool, key='duplicate-sec', headline=news, published=seen, seen=seen,
                       source='sec_edgar', quality='sec_accepted')
        actual = await official(pool, key='issuer-release', headline=news, published=seen, seen=seen)
        old = await official(pool, key='backfill-not-a-signal', headline='ABC Raises Full-Year Revenue Guidance',
                             published=seen - timedelta(days=10), seen=seen)
        first = await run_event_shadow_cycle(pool, now=instant('14:29:50'), quotes=[bar('ABC', instant('14:28:00'))])
        assert first['registered_trials'] == 6
        rows = (await read_event_shadow(pool))['trials']
        assert {row['event_id'] for row in rows} == {actual, old}
        assert all(row['status'] == 'abstained' for row in rows if row['event_id'] == old)
        assert 'old_release_discovered_after_policy_window' in {row['rule'] for row in rows}
        assert {r['sleeve'] for r in rows if r['status'] == 'pending'} == {'long_short'}
        now = instant('14:35:30')
        bars = [bar('ABC', instant('14:34:00')), bar('SPY', instant('14:34:00'), close=600)]
        no_fee = await run_event_shadow_cycle(pool, now=now, quotes=bars, borrow=[loan(annual_rate=None)])
        assert no_fee['pending'] == 1
        too_short = await run_event_shadow_cycle(pool, now=now, quotes=bars,
                                                  borrow=[loan(valid_until=instant('14:45:00'))])
        assert too_short['pending'] == 1
        assert 'borrow_evidence_does_not_cover_planned_hold' in {
            row['reason'] for row in (await read_event_shadow(pool))['trials']
        }
        assert (await read_event_shadow(pool))['books']['long_short']['restricted_cash'] == 0
        opened = await run_event_shadow_cycle(pool, now=now, quotes=bars * 2, borrow=[loan()])
        assert opened['opened'] == 1
        status = await read_event_shadow(pool)
        opened = next(r for r in status['trials'] if r['status'] == 'open')
        assert opened['qty'] <= 50
        assert opened['receipts']['entry']['price_quality'] == 'indicative_bar'
        assert status['books']['long_short']['restricted_cash'] > 7_000
        assert status['books']['long_short']['free_cash'] < 98_000
        later = instant('14:42:15')
        recall = loan(observed_at=instant('14:40:30'), evidence_id='recall-2', recalled=True)
        same_bar = [bar('ABC', instant('14:40:00'), close=95), bar('SPY', instant('14:40:00'), close=598)]
        assert (await run_event_shadow_cycle(pool, now=later, quotes=same_bar, borrow=[recall]))['open'] == 1
        later = instant('14:43:00')
        covered = [bar('ABC', instant('14:41:00'), close=95), bar('SPY', instant('14:41:00'), close=598)]
        assert (await run_event_shadow_cycle(pool, now=later, quotes=covered, borrow=[recall]))['closed'] == 1
        assert (await run_event_shadow_cycle(pool, now=later, quotes=covered, borrow=[recall]))['registered_trials'] == 0
        status = await read_event_shadow(pool)
        result = next(r for r in status['trials'] if r['status'] == 'closed')
        assert result['reason'] == 'borrow_recall' and result['realized_pnl'] > 0 and result['borrow_cost'] > 0
        assert result['stock_return_pct'] == -5 and result['market_return_pct'] < 0
        assert status['books']['long_short']['restricted_cash'] == 0
        assert status['books']['long_short']['free_cash'] == pytest.approx(100_000 + result['realized_pnl'])
        assert status['comparison']['paired_events'] == 2
        assert status['comparison']['paired_trade_events'] == 1
        assert await pool.fetchval('SELECT count(*) FROM sim_order') == 0
        assert await pool.fetchval('SELECT count(*) FROM l2_order') == 0
    finally:
        await pool.close()


@pytest.mark.asyncio
async def test_live_input_adapter_is_used_only_for_due_regular_equity(applied_db, monkeypatch):
    from alpha_agent.paper import event_shadow

    pool = await asyncpg.create_pool(applied_db, min_size=1, max_size=2)
    calls = []

    async def input_adapter(tickers, now):
        calls.append((tickers, now))
        return [bar(ticker, instant('14:34:00')) for ticker in tickers], []

    monkeypatch.setattr(event_shadow, 'read_regular_bars', input_adapter)
    try:
        await run_event_shadow_cycle(pool, now=instant('14:18:00'))
        await official(pool, key='now', headline='ABC Raises Annual Revenue Guidance', published=instant('14:19:00'),
                       seen=instant('14:20:00'))
        await run_event_shadow_cycle(pool, now=instant('14:21:00'))
        assert calls == []
        assert (await run_event_shadow_cycle(pool, now=instant('14:35:30')))['opened'] == 2
        assert calls == [(['ABC', 'SPY'], instant('14:35:30'))]
    finally:
        await pool.close()


@pytest.mark.asyncio
async def test_missing_existing_mark_blocks_new_trade_and_withdrawal_cancels(applied_db):
    pool = await asyncpg.create_pool(applied_db, min_size=1, max_size=2)
    try:
        await run_event_shadow_cycle(pool, now=instant('14:18:00'), quotes=[])
        guide = 'Issuer Raises Annual Revenue Guidance'
        await official(pool, key='abc', headline=guide, published=instant('14:20:00'), seen=instant('14:21:00'))
        await run_event_shadow_cycle(pool, now=instant('14:22:00'), quotes=[])
        assert (await run_event_shadow_cycle(pool, now=instant('14:35:30'),
                                             quotes=[bar('ABC', instant('14:34:00'))]))['opened'] == 2
        seen = instant('14:36:00')
        second = await official(pool, key='xyz', headline=guide, published=seen, seen=seen, ticker='XYZ')
        await run_event_shadow_cycle(pool, now=instant('14:37:00'), quotes=[])
        still = await run_event_shadow_cycle(pool, now=instant('14:39:30'), quotes=[bar('XYZ', instant('14:38:00'))])
        assert still['pending'] == 2
        rows = (await read_event_shadow(pool))['trials']
        assert {row['reason'] for row in rows if row['event_id'] == second and row['status'] == 'pending'} == {
            'awaiting_complete_portfolio_marks'
        }
        await official(pool, key='xyz', headline='Release withdrawn', published=seen, seen=instant('14:40:00'),
                       ticker='XYZ', status='withdrawn')
        marks = [bar(ticker, instant('14:40:00')) for ticker in ('ABC', 'XYZ', 'SPY')]
        fixed = await run_event_shadow_cycle(pool, now=instant('14:41:30'), quotes=marks)
        assert fixed['expired'] == 2 and 'opened' not in fixed
        rows = (await read_event_shadow(pool))['trials']
        assert {row['reason'] for row in rows if row['event_id'] == second and row['status'] == 'expired'} == {
            'official_event_not_current'
        }
    finally:
        await pool.close()


@pytest.mark.asyncio
async def test_margin_breach_uses_a_later_bar_and_cannot_spend_frozen_cash(applied_db):
    pool = await asyncpg.create_pool(applied_db, min_size=1, max_size=2)
    try:
        await run_event_shadow_cycle(pool, now=instant('14:18:00'), quotes=[])
        await official(pool, key='abc', headline='ABC Lowers Annual Earnings Guidance',
                       published=instant('14:20:00'), seen=instant('14:21:00'))
        await run_event_shadow_cycle(pool, now=instant('14:22:00'), quotes=[])
        assert (await run_event_shadow_cycle(pool, now=instant('14:35:30'), borrow=[loan()],
                                             quotes=[bar('ABC', instant('14:34:00'))]))['opened'] == 1
        breach_bar = bar('ABC', instant('14:40:00'), close=200)
        assert (await run_event_shadow_cycle(pool, now=instant('14:41:30'), quotes=[breach_bar]))['open'] == 1
        status = await read_event_shadow(pool)
        pos = next(r for r in status['trials'] if r['status'] == 'open')
        assert pos['receipts']['exit_trigger']['reason'] == 'maintenance_margin'
        assert status['books']['long_short']['restricted_cash'] > 0
        assert (await run_event_shadow_cycle(pool, now=instant('14:43:30'),
                                             quotes=[bar('ABC', instant('14:42:00'), close=190)]))['closed'] == 1
        status = await read_event_shadow(pool)
        result = next(r for r in status['trials'] if r['status'] == 'closed')
        assert result['exit_at'] > as_utc(pos['receipts']['exit_trigger']['known_at'])
        assert result['reason'] == 'maintenance_margin' and result['realized_pnl'] < 0
        assert status['books']['long_short']['restricted_cash'] == 0
        assert status['books']['long_short']['free_cash'] == pytest.approx(100_000 + result['realized_pnl'])
    finally:
        await pool.close()
