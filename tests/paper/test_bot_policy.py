from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from alpha_agent.paper.bot_models import BotConfig, BotDecision
from alpha_agent.paper.bot_policy import model_budget, readiness, research_age
from alpha_agent.paper import bot_runner, bot_store

NOW = datetime(2026, 11, 6, 15, 0, tzinfo=UTC)


def test_exchange_age_future_evidence_and_weekends():
    source = {'scheduled_for_date': '2026-10-30', 'data_asof': '2026-10-30T20:00:00Z'}
    assert research_age(source, datetime(2026, 11, 2, 15, tzinfo=UTC)) == 1
    assert research_age({'scheduled_for_date':'2026-11-06','data_asof':'2026-11-06T20:00:00Z'}, NOW) is None


def test_patient_model_budget_leaves_execution_time():
    assert model_budget({'expires_at':NOW+timedelta(seconds=430)}, NOW)['can_call_model']
    assert not model_budget({'expires_at':NOW+timedelta(seconds=429)}, NOW)['can_call_model']
    assert model_budget({'expires_at':NOW+timedelta(minutes=12)}, NOW)['model_timeout_seconds'] == 250


def test_schedule_disabled_does_not_block_manual_wake():
    cfg = BotConfig().model_dump() | {'credential_configured':True}
    result = readiness(cfg, {'status':'active'}, 0, 0, None, {'allow_writes':True}, NOW)
    assert result['can_wake'] and result['schedule_reason'] == 'schedule_disabled'
    assert result['warnings'] == ['research_unavailable']
    closed = readiness(cfg, {'status':'active'}, 0, 0, None, {'allow_writes':True}, NOW-timedelta(hours=5))
    assert not closed['can_wake'] and 'market_closed' in closed['blocked_reasons']


def test_empty_rebalance_is_not_a_successful_rebalance():
    with pytest.raises(ValueError, match='empty rebalance'):
        BotDecision(context_id='test', decision='rebalance', summary='no actions')
    assert BotDecision(context_id='test', decision='no_trade', summary='hold').target_semantics == 'patch_targets'


async def test_closed_worker_does_not_call_model_or_fetch_context(monkeypatch):
    run = {'id':'one','account_id':1,'stage':'queued','config_version':1,
           'config_snapshot':BotConfig().model_dump(),'expires_at':datetime.now(UTC)+timedelta(minutes=10)}
    monkeypatch.setattr(bot_store, 'claim', AsyncMock(return_value=run))
    monkeypatch.setattr(bot_runner, 'market_session', lambda: {'is_open':False})
    complete, build, model = AsyncMock(), AsyncMock(), AsyncMock()
    monkeypatch.setattr(bot_runner, 'complete_run', complete)
    monkeypatch.setattr(bot_runner, 'build_context', build)
    monkeypatch.setattr(bot_runner, 'model_decision', model)
    pool = type('Pool', (), {'fetchval':AsyncMock(return_value=1),
                             'fetchrow':AsyncMock(return_value={'id':'one','status':'running','stage':'valuing'})})()
    await bot_runner.step(pool)
    assert complete.call_args.args[-1]['outcome_reason'] == 'market_closed'
    build.assert_not_called()
    model.assert_not_called()


async def test_order_readback_uses_actual_terminal_fact():
    import uuid
    ident = uuid.uuid4()
    pool = type('Pool', (), {'fetch':AsyncMock(return_value=[{
        'id':3,'bot_run_id':ident,'action_id':'a','status':'filled','filled_at':NOW,
        'fill_price':10,'transaction_cost':1,'fail_reason':None}])})()
    row = {'id':ident,'result':{'actions':[{'action_id':'a','status':'accepted'}]}}
    result = (await bot_store.enrich_runs(pool, [row]))[0]['result']['actions'][0]
    assert result['status'] == 'accepted' and result['order_status'] == 'filled'
    assert result['filled_price'] == 10 and result['fee'] == 1
