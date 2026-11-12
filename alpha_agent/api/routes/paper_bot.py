"""Owner-scoped bot controls and authenticated, bounded worker invocations."""
from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError

from alpha_agent.api.dependencies import get_db_pool
from alpha_agent.auth.dependencies import require_cron, require_user
from alpha_agent.data.capacity import read_capacity
from alpha_agent.paper import bot_store as store
from alpha_agent.paper.bot_runner import step
from alpha_agent.paper.bot_schedule import enqueue_due, schedule_observations
from alpha_agent.paper.bot_policy import readiness
from alpha_agent.paper.market_clock import NEW_YORK
from alpha_agent.storage.product_ledger import get_latest_canonical_run

router = APIRouter(tags=['paper-bot'])
BASE = '/api/paper/accounts/{account_id}'


async def dispatch_runner():
    token = (os.environ.get('GH_PAT') or '').strip()
    if not token:
        raise HTTPException(503, '机器人运行器未配置，请联系管理员')
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            'https://api.github.com/repos/zzzhhn/alpha-agent/actions/workflows/paper-bot-runner.yml/dispatches',
            headers={'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github+json'},
            json={'ref': 'main'})
    if response.status_code != 204:
        raise HTTPException(503, f'机器人运行器派遣失败（GitHub {response.status_code}），可重新唤起')


@router.get(BASE + '/bot')
async def get_config(account_id: int, user_id: int = Depends(require_user)):
    return await config_with_readiness(await get_db_pool(), user_id, account_id)


async def config_with_readiness(pool, user_id, account_id):
    config = await store.get_config(pool, user_id, account_id)
    account = await store.bot_account(pool, user_id, account_id)
    now = datetime.now(UTC)
    counts = await pool.fetchrow(
        "SELECT count(*) FILTER(WHERE trading_session=$2) AS today, "
        "count(*) FILTER(WHERE status IN ('queued','running')) AS active "
        "FROM sim_bot_run WHERE account_id=$1 AND (trading_session=$2 OR status IN ('queued','running'))",
        account_id, now.astimezone(NEW_YORK).date())
    source = await get_latest_canonical_run(pool)
    config['readiness'] = readiness(config, account, counts['today'], counts['active'],
                                    source, await read_capacity(pool), now)
    slots = await pool.fetch(
        'SELECT session_date,slot,planned_at,observed_at,status,reason,run_id '
        'FROM sim_bot_schedule_slot WHERE account_id=$1 ORDER BY session_date DESC,planned_at DESC LIMIT 10', account_id)
    scheduled_runs = await pool.fetch(
        'SELECT id,trigger,trading_session,created_at,status,finished_at FROM sim_bot_run '
        "WHERE account_id=$1 AND slot_key IS NOT NULL AND trigger IN ('open_after','close_before') "
        'ORDER BY created_at DESC LIMIT 10', account_id)
    config['schedule_observations'] = schedule_observations(config, slots, now, scheduled_runs=scheduled_runs)
    return config


@router.patch(BASE + '/bot')
async def patch_config(account_id: int, body: dict, user_id: int = Depends(require_user)):
    try:
        pool = await get_db_pool()
        await store.save_config(pool, user_id, account_id, body)
        return await config_with_readiness(pool, user_id, account_id)
    except ValidationError:
        raise HTTPException(422, '配置格式或数值范围不正确') from None


@router.get(BASE + '/runs')
async def runs(account_id: int, limit: int = Query(5, ge=1, le=20), offset: int = Query(0, ge=0, le=10000), user_id: int = Depends(require_user)):
    pool = await get_db_pool()
    await store.bot_account(pool, user_id, account_id)
    rows = await pool.fetch(f'SELECT {store.PUBLIC_RUN_COLUMNS} FROM sim_bot_run WHERE account_id=$1 ORDER BY created_at DESC,id DESC LIMIT $2 OFFSET $3', account_id, limit, offset)
    total = await pool.fetchval('SELECT count(*) FROM sim_bot_run WHERE account_id=$1', account_id)
    return {'runs': await store.enrich_runs(pool, rows), 'total': total}


@router.post(BASE + '/runs', status_code=202)
async def wake(account_id: int, user_id: int = Depends(require_user)):
    pool = await get_db_pool()
    config = await config_with_readiness(pool, user_id, account_id)
    blocked = [r for r in config['readiness']['blocked_reasons'] if r != 'run_active']
    if blocked:
        raise HTTPException(409, {'reason': blocked[0], 'readiness': config['readiness']})
    run = await store.enqueue(pool, user_id, account_id)
    try:
        await dispatch_runner()
    except (httpx.HTTPError, HTTPException) as exc:
        # Do not strand an apparently running job after a dispatch failure.
        message = exc.detail if isinstance(exc, HTTPException) else '运行器暂时无法连接，请稍后重试'
        await pool.execute("UPDATE sim_bot_run SET status='failed',stage='failed',error=$2,finished_at=now(),result=jsonb_build_object('outcome_reason','dispatch_failed') WHERE id=$1 AND status='queued'", uuid.UUID(run['id']), message)
        raise HTTPException(503, message) from None
    return run


@router.get(BASE + '/runs/{run_id}')
async def run_detail(account_id: int, run_id: uuid.UUID, user_id: int = Depends(require_user)):
    pool = await get_db_pool()
    return (await store.enrich_runs(pool, [await store.get_run(pool, user_id, account_id, run_id)]))[0]


@router.get(BASE + '/bot/performance')
async def performance(account_id: int, user_id: int = Depends(require_user)):
    from alpha_agent.paper.bot_analytics import read_performance
    return await read_performance(await get_db_pool(), user_id, account_id)


@router.get(BASE + '/bot/position-notes')
async def position_notes(account_id: int, user_id: int = Depends(require_user)):
    """Current holdings' latest model reviews, not an invented entry attribution."""
    pool = await get_db_pool()
    await store.bot_account(pool, user_id, account_id)
    rows = await pool.fetch(
        'SELECT p.ticker,n.note,n.metadata,n.run_id,n.updated_at '
        'FROM sim_position p JOIN sim_account a ON a.id=p.account_id '
        'LEFT JOIN sim_bot_position_note n ON n.account_id=p.account_id AND n.ticker=p.ticker '
        'WHERE p.account_id=$1 AND p.cohort_id=a.reset_count AND p.qty>0 '
        'ORDER BY p.ticker LIMIT 20', account_id)
    notes = []
    for row in rows:
        metadata = store.unpack(row['metadata'])
        notes.append({
            'ticker': row['ticker'], 'note': row['note'],
            'run_id': str(row['run_id']) if row['run_id'] else None,
            'updated_at': row['updated_at'],
            **{key: metadata.get(key) for key in ('thesis', 'invalidation', 'review_after')},
        })
    return {'positions': notes}


@router.post(BASE + '/runs/{run_id}/stop')
async def stop(account_id: int, run_id: uuid.UUID, user_id: int = Depends(require_user)):
    pool = await get_db_pool()
    await store.get_run(pool, user_id, account_id, run_id)
    # Same account→run order as submission: no stop/submit check-then-act race.
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.fetchrow('SELECT id FROM sim_account WHERE id=$1 FOR UPDATE', account_id)
            await conn.execute("UPDATE sim_bot_run SET status='stopped',stage='stopped',finished_at=now(),lease_until=NULL,lease_token=NULL,summary=summary || ' 已停止后续决策；已受理订单仍按原规则结算。' WHERE id=$1 AND status IN ('queued','running')", run_id)
    return store.public_run(await store.get_run(pool, user_id, account_id, run_id))


@router.get(BASE + '/capabilities')
async def capabilities(account_id: int, user_id: int = Depends(require_user)):
    info = await store.get_config(await get_db_pool(), user_id, account_id)
    return {'execution_model': 'intraday_next_bar_v1', 'market': info['market'],
            'actions': ['set_target_weight', 'cancel_order', 'no_trade'],
            'max_positions': info['max_positions'], 'max_position_weight': info['max_position_weight'],
            'external_access': False, 'manual_orders': False, 'shorting': False, 'leverage': False}


@router.get(BASE + '/context')
async def context(account_id: int, user_id: int = Depends(require_user)):
    pool = await get_db_pool()
    await store.bot_account(pool, user_id, account_id)
    row = await pool.fetchrow('SELECT context FROM sim_bot_run WHERE account_id=$1 AND context IS NOT NULL ORDER BY created_at DESC LIMIT 1', account_id)
    return {'context': store.unpack(row['context']) if row else None,
            'reason': None if row else '尚未唤起机器人，暂无研究上下文'}


@router.get('/api/cron/paper_bot/wake', dependencies=[Depends(require_cron)])
async def scheduled_wake():
    """Independent Vercel clock; drive cron carries the durable queue.

    Keep this request short. A successful dispatch is not a completed decision.
    Duplicate clocks share slot keys, and dispatch failures leave queued work
    available for the next carrier rather than erasing the obligation.
    """
    pool = await get_db_pool()
    scheduled = await enqueue_due(pool)
    active = await pool.fetchval(
        "SELECT EXISTS(SELECT 1 FROM sim_bot_run WHERE status IN ('queued','running')) "
        "OR EXISTS(SELECT 1 FROM sim_order WHERE execution_model='intraday_next_bar_v1' AND status='pending')")
    if not active or os.environ.get('PAPER_BOT_GH_FALLBACK') != '1':
        log_clock('vercel_cron', scheduled, dispatched=False)
        return {'ok': True, 'scheduled': scheduled, 'dispatched': False}
    attempted = datetime.now(UTC).isoformat()
    try:
        await dispatch_runner()
    except (httpx.HTTPError, HTTPException):
        log_clock('vercel_cron', scheduled, dispatched=False, dispatch_failed=True)
        await pool.execute(
            "UPDATE sim_bot_run SET diagnostics=diagnostics || $1::jsonb WHERE status IN ('queued','running')",
            store.dump({'dispatch': {'source': 'vercel_cron', 'at': attempted, 'status': 'failed'}}))
        return {'ok': True, 'scheduled': scheduled, 'dispatched': False,
                'reason': 'runner_dispatch_failed'}
    await pool.execute(
        "UPDATE sim_bot_run SET diagnostics=diagnostics || $1::jsonb WHERE status IN ('queued','running')",
        store.dump({'dispatch': {'source': 'vercel_cron', 'at': attempted, 'status': 'requested'}}))
    log_clock('vercel_cron', scheduled, dispatched=True)
    return {'ok': True, 'scheduled': scheduled, 'dispatched': True}


@router.get('/api/cron/paper_bot/drive', dependencies=[Depends(require_cron)])
async def scheduled_drive():
    """One leased worker step, including due-slot enqueue; never a worker loop."""
    return await worker(schedule=True)


@router.post('/api/cron/paper_bot', dependencies=[Depends(require_cron)])
async def worker(schedule: bool = False):
    pool = await get_db_pool()
    scheduled = await enqueue_due(pool) if schedule else None
    if scheduled is not None:
        log_clock('worker_schedule', scheduled)
    # Also finish accepted orders whose run has stopped/expired. Never reopen
    # decisions or call the model merely to settle an existing obligation.
    from alpha_agent.paper.bot_execution import settle_orders
    result = await step(pool)
    settlement = await settle_orders(pool) if not result['processed'] else {}
    pending = await pool.fetchval("SELECT count(*) FROM sim_order WHERE execution_model='intraday_next_bar_v1' AND status='pending'")
    active = await pool.fetchval("SELECT count(*) FROM sim_bot_run WHERE status IN ('queued','running')")
    return {'ok': True, **result, 'active': bool(active or pending),
            'scheduled': scheduled, 'settlement': {k: v for k, v in settlement.items() if k != 'errors'}}


def log_clock(source, scheduled, **outcome):
    """Small carrier receipt, without accounts, holdings, credentials or DB rows."""
    fields = ('observed_at', 'session_date', 'window_open', 'market_open',
              'reason', 'enqueued', 'deduplicated', 'missed_observations')
    print(store.dump({'event': 'paper_bot_clock', 'source': source,
                      **{k: scheduled.get(k) for k in fields}, **outcome}), flush=True)


@router.get('/api/cron/paper_bot/valuation', dependencies=[Depends(require_cron)])
@router.post('/api/cron/paper_bot/valuation', dependencies=[Depends(require_cron)])
async def refresh_valuation():
    from alpha_agent.paper.bot_quote_refresh import refresh_intraday_valuations
    return await refresh_intraday_valuations(await get_db_pool())


@router.post('/api/cron/paper_bot/market_probe', dependencies=[Depends(require_cron)])
async def market_probe(ticker: str = Query('SPY', pattern=r'^[A-Z0-9][A-Z0-9.^=-]{0,19}$')):
    """One public-symbol availability sample, not a trade or blanket SLA."""
    from datetime import UTC, datetime
    from alpha_agent.paper.bot_valuation import valuation_session
    from alpha_agent.paper.intraday import fetch_bars
    from alpha_agent.paper.market_clock import as_utc
    now = datetime.now(UTC)
    session = valuation_session(now)
    try:
        cutoff = now if session['is_open'] else as_utc(session['close_at'])
        bars = await fetch_bars(ticker, cutoff)
        bars = [bar for bar in bars if as_utc(bar['end']) <= cutoff]
        last = bars[-1] if bars else {}
        return {'ok': True, 'available': bool(bars), 'ticker': ticker, 'bars': len(bars),
                'last_bar': last.get('end'), 'price_basis': last.get('price_basis'),
                'observed_at': now.isoformat(),
                'last_bar_age_seconds': (now-as_utc(last['end'])).total_seconds() if last else None,
                'recent_bars': [{'end': bar['end'], 'volume': bar.get('volume')} for bar in bars[-5:]],
                'session_date': session['session_date'], 'is_open': session['is_open']}
    except Exception as exc:
        return {'ok': True, 'available': False, 'ticker': ticker, 'reason': type(exc).__name__}
