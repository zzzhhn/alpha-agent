from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import asyncpg
import pandas as pd
import pytest

from alpha_agent.news import event_reaction as reaction
from alpha_agent.news.event_watch import read_event_evidence

PUB = datetime(2026, 11, 23, 13, 57, 54, tzinfo=UTC)
SEEN = PUB + timedelta(minutes=4)


def bar(end, at, *, opening=100, close=100, action=False, source='raw:fixture'):
    return {'start': end - reaction.MINUTE, 'end': end, 'fetched_at': at,
            'open': opening, 'close': close, 'volume': 100, 'source': source,
            'price_basis': 'raw_unadjusted', 'corporate_actions_known': True, 'corporate_actions': action}


def open_observations(window, now):
    opening_end = window.opening + reaction.MINUTE
    return (
        [bar(window.prior_close, now, close=100), bar(opening_end, now, opening=115, close=116)],
        [bar(window.prior_close, now, close=200), bar(opening_end, now, opening=204, close=205)],
    )


def test_opening_gap_and_follow_through_freeze_distinct_time_windows():
    window = reaction.reaction_window(PUB, SEEN)
    assert window.timing == 'overnight' and window.session == date(2026, 11, 23)
    assert window.prior_close == datetime(2026, 11, 20, 21, tzinfo=UTC)
    waiting = reaction.reaction_step(window, window.opening, {}, [], [])
    assert waiting['status'] == 'pending' and not waiting['gap'] and not waiting['anchor']
    first_poll = window.opening + timedelta(minutes=2)
    stock, spy = open_observations(window, first_poll)
    one = reaction.reaction_step(window, first_poll, waiting, stock, spy)
    assert one['gap']['ticker_return'] == pytest.approx(.15)
    assert one['gap']['spy_return'] == pytest.approx(.02)
    assert one['gap']['excess_return'] == pytest.approx(.13)
    assert one['gap']['price_basis'] == 'raw_unadjusted'
    assert not one['follow_through'] and one['follow_reason'] == 'waiting_30_minute_mark'

    target = window.opening + timedelta(minutes=31)
    received = target + timedelta(minutes=2)
    final = reaction.reaction_step(window, received, one,
        [bar(window.opening + reaction.MINUTE, received, close=80), bar(target, received, close=120)],
        [bar(target, received, close=208)])
    assert final['status'] == 'observed'
    assert final['gap'] == one['gap'] and final['anchor'] == one['anchor']
    assert final['follow_through']['ticker_return'] == pytest.approx(120 / 116 - 1)
    assert final['follow_through']['spy_return'] == pytest.approx(208 / 205 - 1)
    assert final['follow_through']['end_at'] == target.isoformat()


def test_late_discovery_never_gets_open_gap_or_earlier_bar():
    seen = datetime(2026, 11, 23, 15, 7, 12, tzinfo=UTC)
    window = reaction.reaction_window(PUB, seen)
    assert window.timing == 'late_discovery'
    at = datetime(2026, 11, 23, 15, 12, tzinfo=UTC)
    old_bar = bar(datetime(2026, 11, 23, 15, 8, tzinfo=UTC), at)
    new_bar = bar(datetime(2026, 11, 23, 15, 9, tzinfo=UTC), at)
    value = reaction.reaction_step(window, at, {}, [old_bar, new_bar], [old_bar, new_bar])
    assert value['gap'] is None and value['gap_reason'] == 'late_discovery_no_open_gap'
    assert value['anchor']['ticker']['end'] == '2026-11-23T15:09:00+00:00'


def test_early_close_and_holiday_are_calendar_driven():
    holiday = datetime(2026, 11, 26, 18, tzinfo=UTC)
    window = reaction.reaction_window(holiday, holiday + reaction.MINUTE)
    assert window.opening == datetime(2026, 11, 27, 14, 30, tzinfo=UTC)
    assert window.closing == datetime(2026, 11, 27, 18, tzinfo=UTC)
    assert window.prior_close == datetime(2026, 11, 25, 21, tzinfo=UTC)
    pub = window.closing - timedelta(minutes=11)
    last = reaction.reaction_window(pub, pub + reaction.MINUTE)
    result = reaction.reaction_step(last, pub + reaction.MINUTE, {}, [], [])
    assert result['status'] == 'unavailable'
    assert result['follow_reason'] == 'insufficient_regular_session'


def test_missing_quote_and_adjustment_are_explicit_and_never_historical_returns():
    window = reaction.reaction_window(PUB, SEEN)
    now = window.opening + timedelta(minutes=3)
    stock, spy = open_observations(window, now)
    no_benchmark = reaction.reaction_step(window, now, {}, stock, [])
    assert no_benchmark['gap_reason'] == 'missing_open_pair'
    assert no_benchmark['follow_reason'] == 'missing_anchor_pair'
    action = reaction.reaction_step(window, now, {}, stock, [spy[0], dict(spy[1], corporate_actions=True)])
    assert action['status'] == 'unavailable' and action['follow_reason'] == 'corporate_action_or_unknown'
    old = window.opening + timedelta(minutes=45)
    assert not reaction._needs_market(window, {}, old)
    stale = reaction.reaction_step(window, old, {}, stock, spy)
    assert stale['status'] == 'unavailable' and stale['gap_reason'] == 'open_capture_window_elapsed'
    assert stale['follow_reason'] == 'anchor_capture_window_elapsed'


def test_follow_through_requires_exact_benchmark_timestamp_and_receipt():
    window = reaction.reaction_window(PUB, SEEN)
    now = window.opening + timedelta(minutes=2)
    one = reaction.reaction_step(window, now, {}, *open_observations(window, now))
    target = window.opening + timedelta(minutes=31)
    at = target + reaction.MINUTE
    potential = reaction.reaction_step(window, at, one,
        [bar(target, at, close=120)], [bar(target - reaction.MINUTE, at, close=207)])
    assert potential['status'] == 'pending' and potential['follow_reason'] == 'missing_30_minute_pair'
    future = reaction.reaction_step(window, at, one,
        [bar(target, at, close=120)], [bar(target, at + reaction.MINUTE, close=208)])
    assert future['follow_through'] is None
    final = reaction.reaction_step(window, target + timedelta(minutes=10), potential, [], [])
    assert final['status'] == 'partial' and final['follow_through'] is None


@pytest.mark.asyncio
async def test_raw_provider_keeps_actions_and_missing_metadata_session_scoped(monkeypatch):
    frame = pd.DataFrame({'Open': [10, 11, 12], 'Close': [10, 11, 12], 'Volume': [5, 6, 7],
                          'Dividends': [0, 0, float('nan')], 'Stock Splits': [2, 0, 0]},
                         index=pd.to_datetime(['2026-11-20T15:00:00Z', '2026-11-20T15:01:00Z',
                                               '2026-11-23T15:00:00Z']))
    monkeypatch.setattr(reaction, '_history', lambda _: frame)
    old_action, same_day, new_day = await reaction.fetch_reaction_bars('NVDA')
    assert old_action['corporate_actions'] is same_day['corporate_actions'] is True
    assert same_day['corporate_actions_known'] is True
    assert new_day['corporate_actions'] is new_day['corporate_actions_known'] is False


@pytest.mark.asyncio
async def test_two_event_cycle_reuses_spy_and_private_read_excludes_forensic_receipts(applied_db):
    window = reaction.reaction_window(PUB, SEEN)
    now = window.opening + timedelta(minutes=2)
    calls = []

    async def receive(ticker):
        calls.append(ticker)
        return open_observations(window, now)[ticker == 'SPY']

    async with asyncpg.create_pool(applied_db, min_size=1, max_size=2) as pool:
        for t in ('NVDA', 'AAPL', 'AMD'):
            await pool.execute('''INSERT INTO official_event_watch(ticker,source,source_key,content_hash,
                   title,url,published_at,published_at_quality,first_seen_at,kind,status)
                VALUES ($1,'sec_edgar',$1,'test','Issuer announces CEO transition','https://www.sec.gov/',
                   $2, 'sec_accepted', $3, 'management_change','observed')''', t, PUB, SEEN)
        result = await reaction.observe_event_reactions(pool, now=now, fetcher=receive)
        assert result['events_checked'] == result['events_written'] == 2
        assert result['symbols_read'] == 3 and sorted(calls) == ['AAPL', 'NVDA', 'SPY']
        stored = await pool.fetchrow('SELECT observed_at,known_at,gap FROM official_event_reaction')
        assert stored['observed_at'] > stored['known_at']
        assert 'evidence' in reaction._unpack(stored['gap'])
        reply = await read_event_evidence(pool, 1, 'NVDA', 1, now=now)
        visible = reaction.EventReaction.model_validate(reply['events'][0]['reaction'])
        assert visible.status == 'pending' and visible.gap.ticker_return == pytest.approx(.15)
        assert 'evidence' not in reply['events'][0]['reaction']['gap']
