import base64
import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from alpha_agent.auth.crypto_box import decrypt
from alpha_agent.paper import bot_store
from alpha_agent.paper.bot_models import BotConfig


async def test_account_lookup_is_owner_scoped_and_never_falls_back():
    pool = type('Pool', (), {'fetchrow': AsyncMock(return_value=None)})()
    assert await bot_store.credential(pool, 7, 'openai', account_id=3, source='account') is None
    sql, *args = pool.fetchrow.call_args.args
    assert 'a.user_id=$2' in sql and "a.kind='bot'" in sql and 'user_byok' not in sql
    assert args == [3, 7, 'openai']
    pool.fetchrow.assert_awaited_once()


async def test_legacy_config_uses_user_credential():
    config = BotConfig.model_validate({'provider': 'kimi', 'model': 'old'})
    pool = type('Pool', (), {'fetchrow': AsyncMock(return_value={'provider': 'kimi'})})()
    await bot_store.credential(pool, 7, config.provider, account_id=3, source=config.credential_source)
    assert 'FROM user_byok' in pool.fetchrow.call_args.args[0]


class RecordingPool:
    def __init__(self):
        self.writes = []
        self.in_transaction = False

    @asynccontextmanager
    async def acquire(self):
        yield self

    @asynccontextmanager
    async def transaction(self):
        self.in_transaction = True
        try:
            yield self
        finally:
            self.in_transaction = False

    async def fetchrow(self, *_):
        return {'id': 3}

    async def execute(self, sql, *args):
        assert self.in_transaction
        self.writes.append((sql, args))


async def test_private_key_and_config_save_together_without_touching_global_key(monkeypatch):
    pool = RecordingPool()
    master = base64.b64encode(b'a' * 32)
    monkeypatch.setenv('BYOK_MASTER_KEY', master.decode())
    monkeypatch.setattr(bot_store, 'get_config', AsyncMock(return_value=BotConfig().model_dump()))
    monkeypatch.setattr(bot_store, 'credential', AsyncMock(return_value=None))
    await bot_store.save_config(pool, 7, 3, {
        'credential_source': 'account', 'provider': 'openai', 'model': 'gpt-6.1-sol',
        'credential': {'api_key': 'test-only-secret', 'base_url': 'https://api.openai.com/v1'},
    })
    assert len(pool.writes) == 2
    sql, args = pool.writes[0]
    assert 'sim_bot_credential' in sql and args[:2] == (3, 'openai')
    assert decrypt(args[2], args[3], master) == 'test-only-secret'
    assert args[4:] == ('cret', 'https://api.openai.com/v1')
    config_sql, config_args = pool.writes[1]
    assert 'config_version+1' in config_sql
    saved = json.loads(config_args[1])
    assert saved['credential_source'] == 'account'
    assert 'credential' not in saved and 'test-only-secret' not in config_args[1]
    assert all('user_byok' not in sql for sql, _ in pool.writes)


@pytest.mark.parametrize('credential', [
    {'api_key': ''}, {'api_key': 'test-only', 'base_url': 'https://user:password@example.test'},
    {'api_key': 'test-only', 'base_url': 'http://example.test'},
])
async def test_invalid_secret_input_never_writes_or_echoes_key(monkeypatch, credential):
    pool = RecordingPool()
    monkeypatch.setattr(bot_store, 'get_config', AsyncMock(return_value=BotConfig().model_dump()))
    with pytest.raises(HTTPException) as failure:
        await bot_store.save_config(pool, 7, 3, {'credential_source': 'account', 'credential': credential})
    assert failure.value.status_code == 422 and 'test-only' not in str(failure.value.detail)
    assert pool.writes == []


async def test_missing_private_key_does_not_silently_use_global_key(monkeypatch):
    pool = RecordingPool()
    monkeypatch.setattr(bot_store, 'get_config', AsyncMock(return_value=BotConfig().model_dump()))
    lookup = AsyncMock(return_value=None)
    monkeypatch.setattr(bot_store, 'credential', lookup)
    with pytest.raises(HTTPException):
        await bot_store.save_config(pool, 7, 3, {'credential_source': 'account'})
    assert lookup.call_args.kwargs == {'account_id': 3, 'source': 'account'}
    assert pool.writes == []
