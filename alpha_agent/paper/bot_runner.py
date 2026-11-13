"""Durable single-stage worker. Model credentials never enter the job runner."""
from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime

from alpha_agent.api.byok import _build_byok_client
from alpha_agent.auth.crypto_box import decrypt
from alpha_agent.paper import bot_store as store
from alpha_agent.paper.bot_context import build_context, execution_context
from alpha_agent.paper.bot_execution import settle_orders, submit_targets
from alpha_agent.paper.bot_models import BotConfig, BotDecision, DecisionParseError, parse_decision
from alpha_agent.paper.bot_policy import MODEL_TIMEOUT_SECONDS, model_budget
from alpha_agent.paper.bot_prompt import PROMPT_VERSION, SYSTEM as SYSTEM, build_decision_messages
from alpha_agent.paper.market_clock import market_session


async def model_decision(pool, run, context, config):
    owner = await pool.fetchval('SELECT user_id FROM sim_account WHERE id=$1', run['account_id'])
    cred = await store.credential(pool, owner, config.provider)
    if not cred:
        raise ValueError('BYOK 凭据不存在，请在设置中重新保存')
    master = os.environ.get('BYOK_MASTER_KEY')
    if not master:
        raise ValueError('服务器尚未配置 BYOK 解密密钥')
    key = decrypt(cred['ciphertext'], cred['nonce'], master.encode())
    client = _build_byok_client(config.provider, key, cred['base_url'], config.model)
    del key
    try:
        response = await asyncio.wait_for(client.chat(
            build_decision_messages(config, context, llm_calls=run['llm_calls']),
            temperature=0.3, max_tokens=4096), timeout=MODEL_TIMEOUT_SECONDS)
    finally:
        close = getattr(client, 'close', None)
        if close:
            await close()
    # Settings shows "last used"; bot calls are real uses of the stored key.
    await pool.execute('UPDATE user_byok SET last_used_at=now() WHERE user_id=$1 AND provider=$2',
                       owner, config.provider)
    return response


async def step(pool, run_id=None):
    run = await store.claim(pool, run_id)
    if not run:
        return {'processed': False, 'active': False}
    run['_step_started_at'] = datetime.now(UTC)
    try:
        config = BotConfig.model_validate(store.unpack(run['config_snapshot']))
        current = await pool.fetchval('SELECT config_version FROM sim_bot_config WHERE account_id=$1', run['account_id'])
        if current != run['config_version']:
            await store.finish(pool, run, 'stopped', summary='配置已修改，旧决策不再继续提交。已受理订单仍按原规则结算。',
                               result={**store.unpack(run['result']), 'outcome_reason': 'config_changed'})
        elif run['expires_at'] <= datetime.now(UTC) and run['stage'] != 'valuing':
            await settle_orders(pool, run['account_id'])
            await store.finish(pool, run, 'partial' if run['stage'] == 'settling' else 'skipped', summary='本轮执行窗口已结束；未提交动作不转到下一交易日。',
                               result={**store.unpack(run['result']), 'outcome_reason': 'execution_window_expired'})
        elif run['stage'] in ('queued', 'gathering'):
            if not market_session()['is_open']:
                await complete_run(pool, run, 'skipped', '当前不在交易时段，未调用模型、未提交订单。', {'outcome_reason': 'market_closed', 'actions': []})
                return await current_state(pool, run)
            context = await build_context(pool, run)
            if len(store.dump(context).encode()) > 64000:
                raise ValueError('研究上下文超过大小预算')
            await pool.execute("UPDATE sim_bot_run SET context=$3::jsonb WHERE id=$1 AND lease_token=$2 AND status='running'", run['id'], run['lease_token'], store.dump(context))
            await store.diagnose(pool, run, {'prompt_version': PROMPT_VERSION,
                                           'context_bytes': len(store.dump(context).encode()),
                                           'quote_coverage': context['quote_coverage'],
                                           'research_age_sessions': context['research_age_sessions'],
                                           'queue_wait_seconds': max(0, round((run['_step_started_at']-run['created_at']).total_seconds()))})
            await store.release(pool, run, 'deciding')
        elif run['stage'] in ('deciding', 'researching'):
            context = store.unpack(run['context'])
            budget = model_budget(run)
            await store.diagnose(pool, run, {'budget': budget,
                                           'ranking_context': context.get('ranking_context')})
            if not market_session()['is_open']:
                await complete_run(pool, run, 'skipped', '市场已离开交易时段，未继续调用模型。', {'outcome_reason': 'market_closed', 'actions': []})
            elif not budget['can_call_model']:
                await complete_run(pool, run, 'skipped', '剩余时间不足以完成模型响应和订单执行；本轮未继续付费调用。', {'outcome_reason': 'decision_budget_exhausted', 'actions': []})
            elif run['llm_calls'] >= 3:
                await complete_run(pool, run, 'no_trade', '补查额度已用完，证据仍不足，保留现有持仓。', {'outcome_reason': 'evidence_insufficient', 'actions': []})
            else:
                # Reserve budget BEFORE the network call. Recovery never gets
                # unlimited calls when the result was lost after billing.
                reserved = await pool.fetchval("UPDATE sim_bot_run SET llm_calls=llm_calls+1 WHERE id=$1 AND lease_token=$2 AND status='running' AND lease_until>now() AND llm_calls<3 RETURNING llm_calls", run['id'], run['lease_token'])
                if reserved is None:
                    return {'processed': True, 'active': True, 'stage': 'lease_lost'}
                try:
                    response = await model_decision(pool, run, context, config)
                except TimeoutError:
                    await store.finish(pool, run, 'failed', summary='模型未在本轮预算内完成；没有因超时而自动下单。', error='model_timeout', result={'outcome_reason': 'model_timeout'})
                    return await current_state(pool, run)
                saved = await pool.fetchval("UPDATE sim_bot_run SET prompt_tokens=prompt_tokens+$3,completion_tokens=completion_tokens+$4,model=$5 WHERE id=$1 AND lease_token=$2 AND status='running' AND lease_until>now() RETURNING id", run['id'], run['lease_token'], response.prompt_tokens, response.completion_tokens, response.model)
                if saved is None:
                    return {'processed': True, 'active': True, 'stage': 'lease_lost'}
                # Provider completion is not proof that the JSON is complete.
                # Keep metadata, not raw output or validation input values.
                finish_reason = getattr(response, 'finish_reason', None)
                output = {'finish_reason': finish_reason if finish_reason in
                          {'end_turn', 'stop', 'length', 'max_tokens', 'tool_calls', 'stop_sequence', 'content_filter'} else 'unknown',
                          'completion_tokens': response.completion_tokens, 'token_limit': 4096,
                          'at_token_limit': response.completion_tokens >= 4096}
                if finish_reason in {'length', 'max_tokens'}:
                    await store.diagnose(pool, run, {'model_output': {**output, 'parse_status': 'truncated'}})
                    await store.finish(pool, run, 'failed', summary='模型输出达到长度上限，决策不完整；未提交订单，也未自动重试。',
                                       error='output_truncated', result={'outcome_reason': 'output_truncated'})
                    return await current_state(pool, run)
                try:
                    decision = parse_decision(response.content, str(run['id']))
                except DecisionParseError as exc:
                    await store.diagnose(pool, run, {'model_output': {**output, 'parse_status': exc.kind, 'fields': exc.fields}})
                    await store.finish(pool, run, 'failed', summary='模型返回的决策不符合动作／证据契约；未提交订单。', error='invalid_output', result={'outcome_reason': 'invalid_output'})
                    return await current_state(pool, run)
                await store.diagnose(pool, run, {'model_output': {**output, 'parse_status': 'valid'}})
                if decision.decision == 'research' and run['llm_calls'] < 2:
                    if not model_budget(run)['can_call_model']:
                        await complete_run(pool, run, 'no_trade', '模型请求补查，但剩余时间不足以再次研究并执行；保留现有持仓。',
                                           {'decision': decision.model_dump(), 'actions': [], 'outcome_reason': 'research_budget_exhausted'})
                        return await current_state(pool, run)
                    # SQL restricts this to the existing eligible universe;
                    # it never fetches a model-invented URL/ticker remotely.
                    expanded = await build_context(pool, run, decision.research_tickers)
                    expanded['previous_research_request'] = {
                        'tickers': decision.research_tickers,
                        'research_run_id': context.get('research_run_id'),
                        'basis': 'historical_request_not_current_ranking_evidence',
                    }
                    if len(store.dump(expanded).encode()) > 64000:
                        raise ValueError('研究上下文超过大小预算')
                    await pool.execute("UPDATE sim_bot_run SET context=$3::jsonb WHERE id=$1 AND lease_token=$2 AND status='running'", run['id'], run['lease_token'], store.dump(expanded))
                    await store.release(pool, run, 'researching')
                else:
                    result = {'decision': decision.model_dump(), 'actions': [],
                              'outcome_reason': 'targets_proposed' if decision.decision == 'rebalance' else
                              decision.no_trade_reason or ('evidence_insufficient' if decision.decision == 'research' else 'strategy_no_op')}
                    await pool.execute("UPDATE sim_bot_run SET result=$3::jsonb,summary=$4 WHERE id=$1 AND lease_token=$2 AND status='running'", run['id'], run['lease_token'], store.dump(result), decision.summary)
                    if decision.decision != 'rebalance' or not market_session()['is_open']:
                        if not market_session()['is_open']:
                            result['outcome_reason'] = 'market_closed'
                        await save_notes(pool, run, decision, context)
                        await complete_run(pool, run, 'no_trade', decision.summary, result)
                    else:
                        await store.release(pool, run, 'executing')
        elif run['stage'] == 'executing':
            result = store.unpack(run['result'])
            decision = BotDecision.model_validate(result['decision'])
            context = await execution_context(pool, run, store.unpack(run['context']), decision)
            actions = await submit_targets(pool, run, decision, context, config)
            result.update(actions=actions, outcome_reason='orders_accepted' if any(a['status'] in ('accepted','existing') for a in actions) else 'execution_blocked')
            await pool.execute("UPDATE sim_bot_run SET result=$3::jsonb WHERE id=$1 AND lease_token=$2 AND status='running'", run['id'], run['lease_token'], store.dump(result))
            pending = await pool.fetchval("SELECT count(*) FROM sim_order WHERE bot_run_id=$1 AND status='pending'", run['id'])
            if pending:
                await store.release(pool, run, 'settling')
            else:
                await save_notes(pool, run, decision, context)
                failures = await pool.fetchval("SELECT count(*) FROM sim_order WHERE bot_run_id=$1 AND status IN ('failed','expired','cancelled')", run['id'])
                partial = failures or any(a['status'] in ('rejected', 'deferred') for a in actions)
                result['outcome_reason'] = 'execution_blocked' if partial else 'orders_settled' if any(a.get('order_status') == 'filled' for a in actions) else 'targets_unchanged'
                await complete_run(pool, run, 'partial' if partial else 'completed', decision.summary, result)
        elif run['stage'] == 'settling':
            result = store.unpack(run['result'])
            result['settlement'] = await settle_orders(pool, run['account_id'])
            await pool.execute("UPDATE sim_bot_run SET result=$3::jsonb WHERE id=$1 AND lease_token=$2 AND status='running'", run['id'], run['lease_token'], store.dump(result))
            pending = await pool.fetchval("SELECT count(*) FROM sim_order WHERE bot_run_id=$1 AND status='pending'", run['id'])
            if pending:
                await store.release(pool, run, 'settling')
            elif any(a['status'] == 'deferred' for a in result.get('actions', [])):
                await store.release(pool, run, 'executing')
            else:
                failures = await pool.fetchval("SELECT count(*) FROM sim_order WHERE bot_run_id=$1 AND status IN ('failed','expired','cancelled')", run['id'])
                decision = BotDecision.model_validate(result['decision'])
                await save_notes(pool, run, decision, store.unpack(run['context']))
                partial = failures or any(a['status'] == 'rejected' for a in result.get('actions', []))
                result['outcome_reason'] = 'execution_partial' if partial else 'orders_settled'
                await complete_run(pool, run, 'partial' if partial else 'completed', decision.summary, result)
        elif run['stage'] == 'valuing':
            from alpha_agent.paper.bot_valuation import refresh_marks
            result = store.unpack(run['result'])
            valuation = await refresh_marks(pool, run['account_id'])
            result['valuation'] = {k: valuation.get(k) for k in ('valuation_quality', 'portfolio_value', 'valued_at', 'benchmark_quality')}
            await store.finish(pool, run, result.pop('final_status', 'completed'), summary=run['summary'], result=result)
        else:
            raise ValueError('未知运行阶段，请联系管理员')
    except Exception as exc:
        # Never persist raw provider response/body/URL or credentials.
        # Exceptions may originate in a provider adapter. Never persist its body
        # or URL, including ValueErrors that could embed credential-bearing input.
        message = type(exc).__name__
        persisted = await pool.fetchval('SELECT result FROM sim_bot_run WHERE id=$1', run['id'])
        await store.finish(pool, run, 'failed', summary='本轮未继续提交新动作；已成交账本保留。', error=message,
                           result={**store.unpack(persisted), 'outcome_reason': 'stage_failed', 'failed_stage': run['stage']})
    return await current_state(pool, run)


async def current_state(pool, run):
    row = await pool.fetchrow('SELECT * FROM sim_bot_run WHERE id=$1', run['id'])
    return {'processed': True, 'active': row['status'] in store.ACTIVE,
            'run_id': str(row['id']), 'status': row['status'], 'stage': row['stage']}


async def save_notes(pool, run, decision, context):
    known = {i['ticker'] for i in context['instruments']}
    for note in decision.position_notes:
        if note.ticker in known:
            await pool.execute(
                'INSERT INTO sim_bot_position_note(account_id,ticker,note,run_id,metadata) '
                "SELECT $1,$2,$3,$4,$6::jsonb WHERE EXISTS(SELECT 1 FROM sim_bot_run WHERE id=$4 AND lease_token=$5 AND status='running') "
                'ON CONFLICT(account_id,ticker) DO UPDATE SET note=EXCLUDED.note,run_id=EXCLUDED.run_id,metadata=EXCLUDED.metadata,updated_at=now()',
                run['account_id'], note.ticker, note.note, run['id'], run['lease_token'],
                store.dump({'thesis': note.thesis, 'invalidation': note.invalidation, 'review_after': note.review_after}))


async def complete_run(pool, run, status, summary, result):
    # Marking is a separate request so it cannot eat into the model's 250s
    # window. Cash and filled trades are already durable at this point.
    await pool.execute("UPDATE sim_bot_run SET result=$3::jsonb,summary=$4 WHERE id=$1 AND lease_token=$2 AND status='running'", run['id'], run['lease_token'], store.dump({**result, 'final_status': status}), summary)
    await store.release(pool, run, 'valuing')
