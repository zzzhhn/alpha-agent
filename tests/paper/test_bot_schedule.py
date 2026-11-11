from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient

from alpha_agent.paper import bot_schedule


CONFIG = {
    'schedule_enabled': True, 'open_enabled': True, 'close_enabled': True,
    'config_updated_at': '2026-11-06T06:43:13Z',
}


def observe(at, rows=(), config=None):
    return bot_schedule.schedule_observations(config or CONFIG, rows, datetime.fromisoformat(at))


def test_missing_trigger_becomes_visible_without_any_worker_write():
    rows = observe('2026-11-06T15:21:00+00:00')
    opening = next(r for r in rows if r['slot'] == 'open_after')
    assert opening['status'] == 'missed'
    assert opening['reason'] == 'trigger_not_observed'
    assert opening['observed_at'] is None and opening['inferred'] is True
    assert next(r for r in rows if r['slot'] == 'close_before')['status'] == 'planned'


def test_missing_trigger_is_not_missed_before_deadline_or_before_activation():
    rows = observe('2026-11-06T15:03:00+00:00')
    assert next(r for r in rows if r['slot'] == 'open_after')['status'] == 'waiting'
    later_config = CONFIG | {'config_updated_at': '2026-11-06T16:00:00Z'}
    assert all(r['slot'] != 'open_after' for r in observe('2026-11-06T17:00:00+00:00', config=later_config))
    assert observe('2026-11-06T17:00:00+00:00', config=CONFIG | {'schedule_enabled': False}) == []


def test_actual_enqueued_record_is_not_replaced_by_inferred_miss():
    real = {'session_date': '2026-11-06', 'slot': 'open_after', 'planned_at': datetime(2026, 11, 6, 15, tzinfo=UTC),
            'observed_at': datetime(2026, 11, 6, 15, 1, tzinfo=UTC), 'status': 'enqueued', 'reason': None, 'run_id': 'real'}
    rows = observe('2026-11-06T17:00:00+00:00', [real])
    opening = next(r for r in rows if r['slot'] == 'open_after')
    assert opening['run_id'] == 'real' and opening['status'] == 'enqueued'
    assert not opening.get('inferred')


def test_weekend_keeps_friday_miss_but_does_not_invent_weekend_sessions():
    rows = observe('2026-11-07T17:00:00+00:00')
    assert {r['session_date'] for r in rows} == {'2026-11-06', '2026-11-09'}
    assert all(r['status'] == 'missed' for r in rows if r['session_date'] == '2026-11-06')


def test_queue_receipt_survives_missing_schedule_observation_write():
    run = {'id': 'real-run', 'trigger': 'open_after', 'trading_session': '2026-11-06',
           'created_at': datetime(2026, 11, 6, 15, 1, tzinfo=UTC)}
    rows = bot_schedule.schedule_observations(CONFIG, [], datetime(2026, 11, 6, 17, tzinfo=UTC), scheduled_runs=[run])
    opening = next(r for r in rows if r['slot'] == 'open_after')
    assert opening['status'] == 'enqueued' and opening['run_id'] == 'real-run'
    assert opening['observed_at'] == run['created_at'] and not opening.get('inferred')


@pytest.mark.parametrize('active,dispatch_error,expected_status', [(False, False, 200), (True, False, 200), (True, True, 503)])
async def test_authenticated_fallback_only_dispatches_existing_work(monkeypatch, active, dispatch_error, expected_status):
    from alpha_agent.api.routes import paper_bot
    pool = type('Pool', (), {'fetchval': AsyncMock(return_value=active), 'execute': AsyncMock()})()
    monkeypatch.setenv('CRON_SECRET', 'test-cron-only')
    monkeypatch.setattr(paper_bot, 'get_db_pool', AsyncMock(return_value=pool))
    enqueue = AsyncMock(return_value={'enqueued': int(active), 'reason': 'slots_checked'})
    dispatch = AsyncMock(side_effect=HTTPException(503, 'test failure') if dispatch_error else None)
    monkeypatch.setattr(paper_bot, 'enqueue_due', enqueue)
    monkeypatch.setattr(paper_bot, 'dispatch_runner', dispatch)
    app = FastAPI()
    app.include_router(paper_bot.router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as api:
        assert (await api.get('/api/cron/paper_bot/wake')).status_code == 401
        assert enqueue.await_count == 0
        response = await api.get('/api/cron/paper_bot/wake', headers={'Authorization': 'Bearer test-cron-only'})
    assert response.status_code == expected_status
    assert dispatch.await_count == int(active)
    if not dispatch_error:
        assert response.json()['dispatched'] is active
    else:
        assert response.json()['detail']['reason'] == 'runner_dispatch_failed'


@pytest.mark.parametrize('created', [True, False])
async def test_second_clock_counts_reuse_not_a_new_run(monkeypatch, created):
    from alpha_agent.paper.bot_models import BotConfig
    config = BotConfig(schedule_enabled=True).model_dump()
    pool = type('Pool', (), {'fetch': AsyncMock(return_value=[{
        'id': 3, 'user_id': 7, 'config': config, 'config_version': 4,
        'updated_at': datetime(2026, 11, 6, tzinfo=UTC),
    }])})()
    monkeypatch.setattr(bot_schedule, 'read_capacity', AsyncMock(return_value={'allow_writes': True}))
    enqueue = AsyncMock(return_value={'id': 'run', 'slot_key': '3:2026-11-09:close_before',
                                     'queue_created': created})
    monkeypatch.setattr(bot_schedule.store, 'enqueue', enqueue)
    monkeypatch.setattr(bot_schedule, 'record_slot', AsyncMock(return_value=None))
    result = await bot_schedule.enqueue_due(pool, datetime(2026, 11, 9, 20, 34, tzinfo=UTC))
    assert result['enqueued'] == int(created)
    assert result['deduplicated'] == int(not created)
    assert result['window_open'] is True
    enqueue.assert_awaited_once()


async def test_late_github_arrival_is_explicit_and_never_backfills(monkeypatch):
    from alpha_agent.paper.bot_models import BotConfig
    pool = type('Pool', (), {'fetch': AsyncMock(return_value=[{
        'id': 3, 'user_id': 7, 'config': BotConfig(schedule_enabled=True).model_dump(),
        'config_version': 4, 'updated_at': datetime(2026, 11, 6, tzinfo=UTC),
    }])})()
    monkeypatch.setattr(bot_schedule, 'read_capacity', AsyncMock(return_value={'allow_writes': True}))
    enqueue = AsyncMock()
    monkeypatch.setattr(bot_schedule.store, 'enqueue', enqueue)
    monkeypatch.setattr(bot_schedule, 'record_slot', AsyncMock(return_value=None))
    result = await bot_schedule.enqueue_due(pool, datetime(2026, 11, 9, 23, 41, tzinfo=UTC))
    assert result['reason'] == 'outside_schedule_window'
    assert not result['window_open'] and not result['market_open']
    assert result['enqueued'] == 0
    enqueue.assert_not_called()

