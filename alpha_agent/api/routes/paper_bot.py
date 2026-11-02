"""Owner-scoped bot controls and authenticated, bounded worker invocations."""
from __future__ import annotations

import os
import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError

from alpha_agent.api.dependencies import get_db_pool
from alpha_agent.auth.dependencies import require_cron, require_user
from alpha_agent.data.capacity import read_capacity
from alpha_agent.paper import bot_store as store
from alpha_agent.paper.bot_runner import step
from alpha_agent.paper.bot_schedule import enqueue_due

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
    return await store.get_config(await get_db_pool(), user_id, account_id)


@router.patch(BASE + '/bot')
async def patch_config(account_id: int, body: dict, user_id: int = Depends(require_user)):
    try:
        return await store.save_config(await get_db_pool(), user_id, account_id, body)
    except ValidationError:
        raise HTTPException(422, '配置格式或数值范围不正确') from None


@router.get(BASE + '/runs')
async def runs(account_id: int, limit: int = Query(5, ge=1, le=20), offset: int = Query(0, ge=0, le=10000), user_id: int = Depends(require_user)):
    pool = await get_db_pool()
    await store.bot_account(pool, user_id, account_id)
    rows = await pool.fetch(f'SELECT {store.PUBLIC_RUN_COLUMNS} FROM sim_bot_run WHERE account_id=$1 ORDER BY created_at DESC,id DESC LIMIT $2 OFFSET $3', account_id, limit, offset)
    total = await pool.fetchval('SELECT count(*) FROM sim_bot_run WHERE account_id=$1', account_id)
    return {'runs': [store.public_run(r) for r in rows], 'total': total}


@router.post(BASE + '/runs', status_code=202)
async def wake(account_id: int, user_id: int = Depends(require_user)):
    pool = await get_db_pool()
    await store.bot_account(pool, user_id, account_id)
    if not (await read_capacity(pool))['allow_writes']:
        raise HTTPException(503, '数据库可用容量不足，暂不创建新运行；现有账本保留')
    run = await store.enqueue(pool, user_id, account_id)
    try:
        await dispatch_runner()
    except (httpx.HTTPError, HTTPException) as exc:
        # Do not strand an apparently running job after a dispatch failure.
        message = exc.detail if isinstance(exc, HTTPException) else '运行器暂时无法连接，请稍后重试'
        await pool.execute("UPDATE sim_bot_run SET status='failed',stage='failed',error=$2,finished_at=now() WHERE id=$1 AND status='queued'", uuid.UUID(run['id']), message)
        raise HTTPException(503, message) from None
    return run


@router.get(BASE + '/runs/{run_id}')
async def run_detail(account_id: int, run_id: uuid.UUID, user_id: int = Depends(require_user)):
    return store.public_run(await store.get_run(await get_db_pool(), user_id, account_id, run_id))


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


@router.post('/api/cron/paper_bot', dependencies=[Depends(require_cron)])
async def worker(schedule: bool = False):
    pool = await get_db_pool()
    scheduled = await enqueue_due(pool) if schedule else None
    # Also finish accepted orders whose run has stopped/expired. Never reopen
    # decisions or call the model merely to settle an existing obligation.
    from alpha_agent.paper.bot_execution import settle_orders
    result = await step(pool)
    settlement = await settle_orders(pool) if not result['processed'] else {}
    pending = await pool.fetchval("SELECT count(*) FROM sim_order WHERE execution_model='intraday_next_bar_v1' AND status='pending'")
    active = await pool.fetchval("SELECT count(*) FROM sim_bot_run WHERE status IN ('queued','running')")
    return {'ok': True, **result, 'active': bool(active or pending),
            'scheduled': scheduled, 'settlement': {k: v for k, v in settlement.items() if k != 'errors'}}


@router.post('/api/cron/paper_bot/market_probe', dependencies=[Depends(require_cron)])
async def market_probe():
    """One public-symbol availability sample, not a trade or blanket SLA."""
    from datetime import UTC, datetime
    from alpha_agent.paper.bot_valuation import valuation_session
    from alpha_agent.paper.intraday import fetch_bars
    from alpha_agent.paper.market_clock import as_utc
    now = datetime.now(UTC)
    session = valuation_session(now)
    try:
        bars = await fetch_bars('SPY', now if session['is_open'] else as_utc(session['close_at']))
        last = bars[-1] if bars else {}
        return {'ok': True, 'available': bool(bars), 'ticker': 'SPY', 'bars': len(bars),
                'last_bar': last.get('end'), 'price_basis': last.get('price_basis'),
                'session_date': session['session_date'], 'is_open': session['is_open']}
    except Exception as exc:
        return {'ok': True, 'available': False, 'ticker': 'SPY', 'reason': type(exc).__name__}
