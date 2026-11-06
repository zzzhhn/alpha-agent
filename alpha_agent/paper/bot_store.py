"""Durable, owner-scoped bot configuration and runs. No provider calls here."""
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from alpha_agent.api.byok import fetch_user_llm_credential, _PROVIDER_DEFAULTS
from alpha_agent.paper.accounts import resolve_account
from alpha_agent.paper.bot_models import BotConfig
from alpha_agent.paper.market_clock import market_session, target_slot_times

ACTIVE = ('queued', 'running')
PUBLIC_RUN_COLUMNS = 'id,account_id,trigger,trading_session,status,stage,created_at,started_at,finished_at,expires_at,config_version,result,summary,error,provider,model,prompt_tokens,completion_tokens,llm_calls,diagnostics'


def unpack(value):
    return json.loads(value) if isinstance(value, str) else (value or {})


def dump(value):
    return json.dumps(value, ensure_ascii=False, default=str, allow_nan=False)


def public_run(row):
    if row is None:
        return None
    result = dict(row)
    for key in ('context', 'config_snapshot', 'lease_token', 'lease_until'):
        result.pop(key, None)
    result['id'] = str(result['id'])
    result['result'] = unpack(result.get('result')) or None
    diagnostics = unpack(result.pop('diagnostics', None))
    if diagnostics:
        result['result'] = {**(result['result'] or {}), 'diagnostics': diagnostics}
    return result


async def enrich_runs(pool, rows):
    """Join terminal order facts at read time; never mutate historical decisions."""
    runs = [public_run(row) for row in rows]
    if not runs:
        return runs
    orders = await pool.fetch(
        'SELECT id,bot_run_id,action_id,status,filled_at,fill_price,transaction_cost,fail_reason '
        'FROM sim_order WHERE bot_run_id=ANY($1::uuid[]) ORDER BY id LIMIT 400',
        [uuid.UUID(r['id']) for r in runs])
    by_action = {(str(o['bot_run_id']), o['action_id']): dict(o) for o in orders}
    for row in runs:
        result = row.get('result')
        if not result:
            continue
        for action in result.get('actions', []):
            order = by_action.get((row['id'], action.get('action_id')))
            if order:
                action.update(order_status=order['status'], filled_at=order['filled_at'],
                              filled_price=order['fill_price'], fee=order['transaction_cost'],
                              order_reason=order['fail_reason'])
    return runs


async def bot_account(pool, user_id, account_id):
    account = await resolve_account(pool, user_id, account_id)
    if account['kind'] != 'bot':
        raise HTTPException(400, '此操作仅适用于机器人账户')
    return account


async def credential(pool, user_id, provider):
    return await pool.fetchrow(
        'SELECT provider,model,base_url,ciphertext,nonce FROM user_byok '
        'WHERE user_id=$1 AND provider=$2', user_id, provider)


def next_wake(config, now=None):
    now = now or datetime.now(UTC)
    if not config.schedule_enabled:
        return None
    for offset in range(8):
        slots = target_slot_times(now + timedelta(days=offset))
        for name, enabled in [('open_after', config.open_enabled), ('close_before', config.close_enabled)]:
            stamp = datetime.fromisoformat(slots[name])
            if enabled and stamp > now:
                return stamp.isoformat()
    return None


async def get_config(pool, user_id, account_id):
    await bot_account(pool, user_id, account_id)
    row = await pool.fetchrow('SELECT * FROM sim_bot_config WHERE account_id=$1', account_id)
    if row:
        config = BotConfig.model_validate(unpack(row['config']))
        version = row['config_version']
    else:
        stored = await fetch_user_llm_credential(pool, user_id)
        provider = stored['provider'] if stored else 'kimi'
        model = (stored['model'] if stored else None) or _PROVIDER_DEFAULTS[provider]['model']
        config = BotConfig(provider=provider, model=model)
        version = 0
    stored = await credential(pool, user_id, config.provider)
    return {**config.model_dump(), 'account_id': account_id, 'config_version': version,
            'credential_configured': bool(stored), 'next_wake_at': next_wake(config),
            'market': market_session()}


async def save_config(pool, user_id, account_id, patch):
    current = await get_config(pool, user_id, account_id)
    config = BotConfig.model_validate({**{k: current[k] for k in BotConfig.model_fields}, **patch})
    if not await credential(pool, user_id, config.provider):
        raise HTTPException(400, '所选模型服务尚未保存 BYOK，请先前往设置')
    if not config.model.strip():
        config.model = _PROVIDER_DEFAULTS[config.provider]['model']
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.fetchrow('SELECT id FROM sim_account WHERE id=$1 AND user_id=$2 FOR UPDATE', account_id, user_id)
            await conn.execute(
                'INSERT INTO sim_bot_config(account_id,config) VALUES($1,$2::jsonb) '
                'ON CONFLICT(account_id) DO UPDATE SET config=EXCLUDED.config, '
                'config_version=sim_bot_config.config_version+1,updated_at=now()', account_id, dump(config.model_dump()))
    return await get_config(pool, user_id, account_id)


async def enqueue(pool, user_id, account_id, *, trigger='manual', slot_key=None, now=None):
    now = now or datetime.now(UTC)
    info = await get_config(pool, user_id, account_id)
    if not info['credential_configured']:
        raise HTTPException(400, '缺少 BYOK，请先在设置保存模型密钥')
    if not info['config_version']:
        info = await save_config(pool, user_id, account_id, {})
    config = BotConfig.model_validate({k: info[k] for k in BotConfig.model_fields})
    session = now.astimezone(ZoneInfo('America/New_York')).date()
    expires = now + timedelta(minutes=12)
    market = market_session(now)
    if market['is_open']:
        expires = min(expires, datetime.fromisoformat(market['close_at']) - timedelta(minutes=1))
    if expires <= now:
        raise HTTPException(409, '临近闭市，本次不创建过期交易计划')
    async with pool.acquire() as conn:
        async with conn.transaction():
            account = await conn.fetchrow('SELECT * FROM sim_account WHERE id=$1 AND user_id=$2 FOR UPDATE', account_id, user_id)
            if account is None or account['kind'] != 'bot' or account['status'] != 'active':
                raise HTTPException(409, '机器人账户当前不可运行')
            active = await conn.fetchrow("SELECT * FROM sim_bot_run WHERE account_id=$1 AND status IN ('queued','running')", account_id)
            if active:
                return public_run(active)
            if slot_key:
                prior = await conn.fetchrow('SELECT * FROM sim_bot_run WHERE slot_key=$1', slot_key)
                if prior:
                    return public_run(prior)
            count = await conn.fetchval('SELECT count(*) FROM sim_bot_run WHERE account_id=$1 AND trading_session=$2', account_id, session)
            if count >= config.max_daily_runs:
                raise HTTPException(429, '本交易日唤起额度已用完')
            row = await conn.fetchrow(
                'INSERT INTO sim_bot_run(id,account_id,trigger,slot_key,trading_session,expires_at,config_version,config_snapshot,provider,model) '
                'VALUES($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9,$10) RETURNING *',
                uuid.uuid4(), account_id, trigger, slot_key, session, expires,
                info['config_version'], dump(config.model_dump()), config.provider, config.model)
    return public_run(row)


async def get_run(pool, user_id, account_id, run_id):
    await bot_account(pool, user_id, account_id)
    row = await pool.fetchrow(f'SELECT {PUBLIC_RUN_COLUMNS} FROM sim_bot_run WHERE id=$1 AND account_id=$2', uuid.UUID(str(run_id)), account_id)
    if row is None:
        raise HTTPException(404, '运行记录不存在')
    return row


async def claim(pool, run_id=None):
    token = uuid.uuid4()
    row = await pool.fetchrow(
        "UPDATE sim_bot_run SET status='running',started_at=COALESCE(started_at,now()), "
        "lease_until=now()+interval '290 seconds',lease_token=$1 "
        "WHERE id=(SELECT id FROM sim_bot_run WHERE status IN ('queued','running') "
        "AND (lease_until IS NULL OR lease_until<now()) AND ($2::uuid IS NULL OR id=$2) "
        "ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED) RETURNING *",
        token, uuid.UUID(str(run_id)) if run_id else None)
    return dict(row) if row else None


async def finish(pool, run, status, *, summary='', error=None, result=None):
    await record_stage(pool, run)
    await pool.execute(
        'UPDATE sim_bot_run SET status=$3,stage=$3,summary=$4,error=$5,result=COALESCE($6::jsonb,result),'
        'finished_at=now(),lease_until=NULL,lease_token=NULL '
        "WHERE id=$1 AND lease_token=$2 AND status='running'",
        run['id'], run['lease_token'], status, summary[:1600], error[:500] if error else None,
        dump(result) if result is not None else None)


async def release(pool, run, stage):
    await record_stage(pool, run)
    await pool.execute("UPDATE sim_bot_run SET stage=$3,lease_until=NULL,lease_token=NULL WHERE id=$1 AND lease_token=$2 AND status='running'",
                       run['id'], run['lease_token'], stage)


async def record_stage(pool, run):
    started = run.get('_step_started_at')
    if started is None:
        return
    ended = datetime.now(UTC)
    event = {'stage': run['stage'], 'started_at': started.isoformat(), 'finished_at': ended.isoformat(),
             'duration_ms': round((ended-started).total_seconds()*1000)}
    await pool.execute(
        "UPDATE sim_bot_run SET diagnostics=jsonb_set(diagnostics,'{stages}',"
        "COALESCE(diagnostics->'stages','[]'::jsonb) || $3::jsonb) "
        "WHERE id=$1 AND lease_token=$2 AND status='running'",
        run['id'], run['lease_token'], dump([event]))


async def diagnose(pool, run, values):
    await pool.execute("UPDATE sim_bot_run SET diagnostics=diagnostics || $3::jsonb "
                       "WHERE id=$1 AND lease_token=$2 AND status='running'",
                       run['id'], run['lease_token'], dump(values))
