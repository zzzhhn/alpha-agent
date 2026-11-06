from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from alpha_agent.paper.bot_store import enrich_runs
from alpha_agent.paper.bot_schedule import schedule_observations
from alpha_agent.paper.bot_context import recommendation_evidence


def test_bot_receives_the_published_recommendation_attribution_and_source_horizon():
    packet = recommendation_evidence({'top_drivers': ['factor', 'analyst', 'rsrs'],
                                      'top_drags': [], 'policy_id': 'tactical', 'horizon_days': 5})
    assert packet['drivers'] == ['factor', 'analyst', 'rsrs']
    assert packet['drags'] == []
    assert packet['recommendation_horizon_days'] == 5
    assert packet['attribution_basis'] == 'signal_names_not_full_research'
    assert recommendation_evidence({'drivers': ['legacy']})['drivers'] == ['legacy']
    assert recommendation_evidence({'top_drivers': [], 'drivers': ['stale']})['drivers'] == []
    assert recommendation_evidence({'top_drivers': 'not a list'})['drivers'] == []


async def test_summary_uses_actual_orders_not_planned_or_accepted_actions():
    run_id = uuid4()
    pool = type('Pool', (), {'fetch': AsyncMock(return_value=[
        {'id': 1, 'bot_run_id': run_id, 'action_id': 'a1', 'status': 'filled', 'qty': 2,
         'filled_at': datetime.now(UTC), 'fill_price': 10, 'transaction_cost': 0.2, 'fail_reason': None},
        {'id': 2, 'bot_run_id': run_id, 'action_id': 'a2', 'status': 'pending', 'qty': 3,
         'filled_at': None, 'fill_price': None, 'transaction_cost': None, 'fail_reason': None},
    ])})()
    result = (await enrich_runs(pool, [{'id': run_id, 'result': {'actions': [
        {'action_id': 'a1', 'status': 'accepted'}, {'action_id': 'a2', 'status': 'accepted'},
        {'action_id': 'rejected-no-order', 'status': 'rejected'},
    ]}}]))[0]
    assert result['order_summary'] == {'total': 2, 'filled': 1, 'pending': 1, 'failed': 0,
                                      'expired': 0, 'cancelled': 0, 'filled_notional': 20, 'paid_fees': 0.2}
    assert result['result']['actions'][0]['order_status'] == 'filled'
    assert result['result']['actions'][1]['order_status'] == 'pending'
    pool.fetch.return_value[0]['transaction_cost'] = None
    assert (await enrich_runs(pool, [{'id': run_id, 'result': None}]))[0]['order_summary']['paid_fees'] is None


@pytest.mark.parametrize('status', ['running', 'completed', 'no_trade', 'failed', 'partial', 'stopped'])
def test_schedule_reports_actual_run_lifecycle(status):
    created = datetime(2026, 11, 6, 20, 31, tzinfo=UTC)
    rows = schedule_observations({'schedule_enabled': False}, [], created, scheduled_runs=[{
        'id': 'run', 'trigger': 'close_before', 'trading_session': '2026-11-06',
        'created_at': created, 'status': status, 'finished_at': created,
    }])
    assert rows[0]['status'] == status
    assert rows[0]['run_id'] == 'run'


async def test_position_reviews_are_owner_checked_bounded_and_missing_is_not_invented(monkeypatch):
    from alpha_agent.api.routes import paper_bot
    run_id = uuid4()
    pool = type('Pool', (), {'fetch': AsyncMock(return_value=[
        {'ticker': 'ABC', 'note': 'Recorded model review', 'metadata': {'thesis': 'Model thesis'},
         'run_id': run_id, 'updated_at': datetime.now(UTC)},
        {'ticker': 'XYZ', 'note': None, 'metadata': None, 'run_id': None, 'updated_at': None},
    ])})()
    owner = AsyncMock()
    monkeypatch.setattr(paper_bot, 'get_db_pool', AsyncMock(return_value=pool))
    monkeypatch.setattr(paper_bot.store, 'bot_account', owner)
    result = await paper_bot.position_notes(3, user_id=7)
    owner.assert_awaited_once_with(pool, 7, 3)
    query, account = pool.fetch.call_args.args
    assert account == 3 and 'p.cohort_id=a.reset_count' in query and 'LIMIT 20' in query
    assert result['positions'][0]['run_id'] == str(run_id)
    assert result['positions'][1]['thesis'] is None
    owner.side_effect = paper_bot.HTTPException(404, 'not found')
    with pytest.raises(paper_bot.HTTPException):
        await paper_bot.position_notes(3, user_id=8)
    assert pool.fetch.await_count == 1
