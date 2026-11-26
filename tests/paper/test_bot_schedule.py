from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import asyncpg
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


@pytest.mark.parametrize('fallback,active,dispatch_error,dispatched', [
    (False, True, False, False),   # default: Vercel drive cron is the carrier
    (True, False, False, False),   # fallback on, nothing queued
    (True, True, False, True),
    (True, True, True, False),     # fallback dispatch failure is non-fatal
])
async def test_wake_only_dispatches_github_when_fallback_enabled(monkeypatch, fallback, active, dispatch_error, dispatched):
    from alpha_agent.api.routes import paper_bot
    pool = type('Pool', (), {'fetchval': AsyncMock(return_value=active), 'execute': AsyncMock()})()
    monkeypatch.setenv('CRON_SECRET', 'test-cron-only')
    monkeypatch.setenv('PAPER_BOT_GH_FALLBACK', '1' if fallback else '0')
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
    assert response.status_code == 200
    assert dispatch.await_count == int(fallback and active)
    assert response.json()['dispatched'] is dispatched


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


async def test_scheduler_reaches_account_23_after_first_bounded_batch(monkeypatch, applied_db):
    from alpha_agent.paper.bot_models import BotConfig

    conn = await asyncpg.connect(applied_db)
    try:
        await conn.execute(
            "INSERT INTO users(email) SELECT 'schedule-' || id || '@test.com' FROM generate_series(1,23) AS id"
        )
        await conn.execute("INSERT INTO sim_account(user_id,kind) SELECT id,'bot' FROM users")
        await conn.execute(
            "INSERT INTO sim_bot_config (account_id,config,updated_at) "
            "SELECT id,$1,$2 FROM sim_account",
            BotConfig(schedule_enabled=True).model_dump_json(),
            datetime(2026, 11, 6, tzinfo=UTC),
        )
        account_ids = [r['id'] for r in await conn.fetch("SELECT id FROM sim_account ORDER BY id")]
        monkeypatch.setattr(bot_schedule, 'read_capacity', AsyncMock(return_value={'allow_writes': True}))
        enqueue_attempts = []

        async def enqueue(pool, user_id, account_id, *, trigger, slot_key, now):
            enqueue_attempts.append(account_id)
            raise HTTPException(400, 'fixture blocks without accessing any credential')

        monkeypatch.setattr(bot_schedule.store, 'enqueue', enqueue)
        first = await bot_schedule.enqueue_due(conn, datetime(2026, 11, 9, 20, 31, tzinfo=UTC))
        second = await bot_schedule.enqueue_due(conn, datetime(2026, 11, 9, 20, 32, tzinfo=UTC))
        assert first['observed_accounts'] == second['observed_accounts'] == 20
        assert enqueue_attempts[:20] == account_ids[:20]
        assert enqueue_attempts[20:23] == account_ids[20:]
        assert await conn.fetchval(
            "SELECT count(*) FROM sim_bot_schedule_slot WHERE slot='close_before' AND status='blocked'"
        ) == 23
    finally:
        await conn.close()



async def test_expiring_blocked_slot_keeps_last_observed_cause(applied_db):
    async with asyncpg.create_pool(applied_db, min_size=1, max_size=1) as pool:
        user = await pool.fetchval("INSERT INTO users(email) VALUES('slots@example.test') RETURNING id")
        account = await pool.fetchval("INSERT INTO sim_account(user_id,kind) VALUES($1,'bot') RETURNING id", user)
        row = {"id": account, "config_version": 1}
        slots = {"session_date": "2026-11-09"}
        stamp = datetime(2026, 11, 9, 15, tzinfo=UTC)
        args = (pool, row, slots, "open_after", stamp)
        await bot_schedule.record_slot(*args, stamp, "blocked", "credential_missing", None)
        end = stamp + timedelta(minutes=20)
        await bot_schedule.record_slot(*args, end, "missed", "slot_expired", None)
        await bot_schedule.record_slot(*args, end + timedelta(minutes=1), "missed", "slot_expired", None)
        record = await pool.fetchrow("SELECT status,reason,observed_at FROM sim_bot_schedule_slot WHERE account_id=$1", account)
        assert tuple(record) == ("missed", "credential_missing", end)
