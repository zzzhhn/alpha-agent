"""Small pure checks plus one opt-in local SQL/API/LLM-adapter flow."""
import base64
import json
import os
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from urllib.parse import urlsplit

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from alpha_agent.paper import bot_runner, bot_schedule, bot_store
from alpha_agent.paper.bot_models import BotConfig, parse_decision


def test_decision_rejects_context_spoof_and_extra_permissions():
    packet = {'context_id': 'one', 'decision': 'no_trade', 'summary': '现金观望'}
    assert parse_decision(json.dumps(packet), 'one').actions == []
    with pytest.raises(ValueError):
        parse_decision(json.dumps(packet), 'other')
    with pytest.raises(ValueError):
        parse_decision(json.dumps(packet | {'account_id': 5}), 'one')


def test_next_wake_obeys_dst_half_days_and_disabled():
    assert bot_store.next_wake(BotConfig(), datetime(2026, 11, 2, 12, tzinfo=UTC)) is None
    config = BotConfig(schedule_enabled=True)
    assert bot_store.next_wake(config, datetime(2026, 11, 2, 12, tzinfo=UTC)) == '2026-11-02T15:00:00+00:00'
    assert bot_store.next_wake(config, datetime(2026, 11, 27, 16, tzinfo=UTC)) == '2026-11-27T17:30:00+00:00'


@pytest.mark.skipif(not os.environ.get('ALPHA_PAPER_BOT_TEST_DSN'), reason='explicit local test DB only')
async def test_sql_owner_api_byok_worker_and_scheduler(monkeypatch):
    import asyncpg
    from alpha_agent.api.routes import paper, paper_bot
    from alpha_agent.auth.crypto_box import encrypt
    from alpha_agent.auth.dependencies import require_user
    from alpha_agent.llm.base import LLMResponse
    from alpha_agent.paper import bot_valuation

    dsn = os.environ['ALPHA_PAPER_BOT_TEST_DSN']
    assert urlsplit(dsn).hostname in ('localhost', '127.0.0.1')
    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=2)
    # Idempotent additive nullable correction to this disposable test schema.
    await pool.execute('ALTER TABLE sim_equity_daily ALTER COLUMN portfolio_value DROP NOT NULL; ALTER TABLE sim_equity_daily ALTER COLUMN unrealized_pnl DROP NOT NULL')
    user = await pool.fetchval('INSERT INTO users(email) VALUES($1) RETURNING id', f'runner-{uuid.uuid4()}@example.test')
    other = await pool.fetchval('INSERT INTO users(email) VALUES($1) RETURNING id', f'other-{uuid.uuid4()}@example.test')
    master = base64.b64encode(os.urandom(32))
    monkeypatch.setenv('BYOK_MASTER_KEY', master.decode())
    ciphertext, nonce = encrypt('local-test-credential', master)
    await pool.execute("INSERT INTO user_byok(user_id,provider,ciphertext,nonce,last4,model) VALUES($1,'kimi',$2,$3,'test','selected-model')", user, ciphertext, nonce)
    monkeypatch.setattr(paper, 'get_db_pool', AsyncMock(return_value=pool))
    monkeypatch.setattr(paper_bot, 'get_db_pool', AsyncMock(return_value=pool))
    monkeypatch.setattr(paper_bot, 'dispatch_runner', AsyncMock())
    monkeypatch.setattr(paper_bot, 'read_capacity', AsyncMock(return_value={'allow_writes': True}))
    monkeypatch.setattr(bot_schedule, 'read_capacity', AsyncMock(return_value={'allow_writes': True}))
    monkeypatch.setattr(bot_valuation, 'refresh_marks', AsyncMock(return_value={'valuation_quality': 'cash_only', 'portfolio_value': 10000}))
    app = FastAPI()
    app.include_router(paper.router)
    app.include_router(paper_bot.router)
    current_user = [user]
    app.dependency_overrides[require_user] = lambda: current_user[0]
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as api:
            accounts = (await api.get('/api/paper/accounts')).json()['accounts']
            assert len(accounts) == 1 and accounts[0]['kind'] == 'human'
            human_id = accounts[0]['account_id']
            human_before = dict(await pool.fetchrow('SELECT * FROM sim_account WHERE id=$1', human_id))
            result = await api.post('/api/paper/accounts', json={'name': '持久 bot', 'initial_cash': 10000})
            assert result.status_code == 201, result.text
            bot_id = result.json()['account_id']
            root = f'/api/paper/accounts/{bot_id}'
            config = (await api.get(root + '/bot')).json()
            assert config['credential_configured'] and config['model'] == 'selected-model'
            assert 'ciphertext' not in json.dumps(config)
            current_user[0] = other
            assert (await api.get(root + '/bot')).status_code == 404
            assert (await api.get(root + '/runs')).status_code == 404
            current_user[0] = user
            saved = await api.patch(root + '/bot', json={'schedule_enabled': True})
            assert saved.status_code == 200, saved.text
            response = await api.post(root + '/runs', json={})
            assert response.status_code == 202, response.text
            run_id = response.json()['id']
            assert (await api.post(root + '/runs', json={})).json()['id'] == run_id
            async def chat(messages, **kwargs):
                packet = json.loads(messages[1].content)
                assert packet['context']['account']['account_id'] == bot_id
                return LLMResponse(json.dumps({'context_id': run_id, 'decision': 'no_trade', 'summary': '休市，保留现金。'}), 'selected-model', 100, 30)
            fake = type('Client', (), {})()
            fake.chat, fake.close = chat, AsyncMock()
            def client(provider, key, base, model):
                assert (provider, key, model) == ('kimi', 'local-test-credential', 'selected-model')
                return fake
            monkeypatch.setattr(bot_runner, '_build_byok_client', client)
            assert (await bot_runner.step(pool, run_id))['stage'] == 'deciding'
            assert (await bot_runner.step(pool, run_id))['stage'] == 'valuing'
            assert (await bot_runner.step(pool, run_id))['status'] == 'no_trade'
            detail = (await api.get(root + '/runs/' + run_id)).json()
            assert detail['prompt_tokens'] == 100 and detail['llm_calls'] == 1
            assert 'lease_token' not in detail and 'config_snapshot' not in detail
            assert dict(await pool.fetchrow('SELECT * FROM sim_account WHERE id=$1', human_id)) == human_before
            assert await pool.fetchval('SELECT count(*) FROM sim_order WHERE account_id=$1', bot_id) == 0
            # Same due slot cannot create a second run after config changes.
            at = datetime(2026, 11, 2, 15, 2, tzinfo=UTC)
            assert (await bot_schedule.enqueue_due(pool, at))['enqueued'] >= 1
            scheduled = await pool.fetchrow("SELECT * FROM sim_bot_run WHERE account_id=$1 AND trigger='open_after'", bot_id)
            assert scheduled
            await pool.execute("UPDATE sim_bot_run SET status='completed' WHERE id=$1", scheduled['id'])
            await bot_store.save_config(pool, user, bot_id, {'instructions': '新说明'})
            await bot_schedule.enqueue_due(pool, at)
            assert await pool.fetchval("SELECT count(*) FROM sim_bot_run WHERE account_id=$1 AND trigger='open_after'", bot_id) == 1
            # Stop is durable and leaves the human and accepted ledger alone.
            run = await bot_store.enqueue(pool, user, bot_id)
            stopped = await api.post(root + '/runs/' + run['id'] + '/stop')
            assert stopped.json()['status'] == 'stopped'
            assert (await bot_runner.step(pool, run['id']))['processed'] is False
            assert (await api.get('/api/paper/account')).json()['account_id'] == human_id
    finally:
        await pool.close()
