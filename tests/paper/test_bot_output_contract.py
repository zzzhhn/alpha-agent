import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from alpha_agent.llm.base import LLMResponse
from alpha_agent.paper import bot_runner, bot_store
from alpha_agent.paper.bot_models import BotConfig, DecisionParseError, parse_decision


@pytest.mark.parametrize(('content', 'kind'), [
    ('{"decision":', 'invalid_json'),
    (json.dumps({'context_id': 'one', 'decision': 'no_trade', 'summary': 'ok', 'private-payload': 'secret'}), 'schema_mismatch'),
    (json.dumps({'context_id': 'wrong', 'decision': 'no_trade', 'summary': 'ok'}), 'context_mismatch'),
])
def test_safe_parse_diagnostics(content, kind):
    with pytest.raises(DecisionParseError) as error:
        parse_decision(content, 'one')
    assert error.value.kind == kind
    assert 'secret' not in str(error.value) + str(error.value.fields)
    assert 'private-payload' not in str(error.value.fields)


@pytest.mark.parametrize(('finish_reason', 'content', 'expected'), [
    ('max_tokens', '{"decision":', 'output_truncated'),
    ('end_turn', '{"decision":', 'invalid_output'),
])
async def test_output_failure_is_terminal_without_orders_or_model_retry(monkeypatch, finish_reason, content, expected):
    run = {'id': 'one', 'account_id': 1, 'stage': 'deciding', 'config_version': 1,
           'config_snapshot': BotConfig().model_dump(), 'context': {}, 'lease_token': 'lease',
           'expires_at': datetime.now(UTC) + timedelta(minutes=10), 'llm_calls': 0}
    monkeypatch.setattr(bot_store, 'claim', AsyncMock(return_value=run))
    monkeypatch.setattr(bot_runner, 'market_session', lambda: {'is_open': True})
    monkeypatch.setattr(bot_runner, 'model_budget', lambda _: {'can_call_model': True})
    model = AsyncMock(return_value=LLMResponse(content, 'saved-model', 10, 4096, finish_reason))
    finish, diagnose, submit = AsyncMock(), AsyncMock(), AsyncMock()
    monkeypatch.setattr(bot_runner, 'model_decision', model)
    monkeypatch.setattr(bot_runner, 'submit_targets', submit)
    monkeypatch.setattr(bot_store, 'finish', finish)
    monkeypatch.setattr(bot_store, 'diagnose', diagnose)
    pool = type('Pool', (), {'fetchval': AsyncMock(return_value=1),
                             'fetchrow': AsyncMock(return_value={'id': 'one', 'status': 'failed', 'stage': 'failed'})})()
    assert (await bot_runner.step(pool))['status'] == 'failed'
    model.assert_awaited_once()
    submit.assert_not_called()
    assert finish.call_args.kwargs['error'] == expected
    diagnostic = diagnose.call_args.args[2]['model_output']
    assert diagnostic['finish_reason'] == finish_reason
    assert content not in json.dumps(diagnostic)
