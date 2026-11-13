import json

from alpha_agent.paper.bot_context import decision_history, ranking_context
from alpha_agent.paper.bot_runner import SYSTEM


def test_current_snapshot_does_not_repeat_old_top_eight_claim():
    # Production incident: COIN entered at 6 while held FRT fell to 10.
    tickers = ['GPN', 'ERIE', 'REGN', 'FDXF', 'LNT', 'COIN', 'KIM', 'SYK', 'AMZN', 'FRT']
    rows = [{'ticker': t, 'rank': n} for n, t in enumerate(tickers, 1)]
    held = ['ERIE', 'FDXF', 'FRT', 'GPN', 'KIM', 'LNT', 'REGN', 'SYK']
    facts = ranking_context(rows, held, 8, {'id': 78, 'data_asof': '2026-11-07'})
    assert facts['research_run_id'] == 78
    assert facts['holdings_equal_top_n'] is False
    assert facts['held_in_top_n'] == 7
    assert facts['held_outside_top_n'] == ['FRT']
    assert facts['top_n_not_held'] == ['COIN']
    assert facts['held_ranks']['FRT'] == 10
    history = decision_history([{
        'id': 'old', 'created_at': '2026-11-06', 'status': 'no_trade',
        'research_run_id': '77', 'summary': '持仓与前8完全一致。',
        'result': {'decision': {'decision': 'no_trade', 'summary': 'old ranking claim'},
                   'outcome_reason': 'keep_positions'},
    }])
    assert history[0]['research_run_id'] == '77'
    assert history[0]['outcome_reason'] == 'keep_positions'
    assert 'summary' not in json.dumps(history)
    assert '完全一致' not in json.dumps(history, ensure_ascii=False)
    assert 'ranking_context' in SYSTEM and 'not expected returns' in SYSTEM


def test_incomplete_ranks_are_not_presented_as_confirmed_portfolio_overlap():
    facts = ranking_context([{'ticker': 'A', 'rank': 1}], ['A', 'UNKNOWN'], 8, None)
    assert facts['holdings_equal_top_n'] is None
    assert facts['held_rank_unknown'] == ['UNKNOWN']
    assert facts['held_outside_top_n'] == []
    assert ranking_context([{'ticker': 'A', 'rank': 1}], ['A'], 1, {'id': 1, 'data_asof': None})['holdings_equal_top_n'] is True
    assert decision_history([{'id': 'failed', 'created_at': None, 'status': 'failed',
                              'result': None}])[0]['decision'] is None


def test_fact_discipline_prompt_is_versioned_and_states_the_owner_rules():
    from alpha_agent.paper.bot_runner import PROMPT_VERSION

    assert PROMPT_VERSION.startswith('bot-system-v2-20261113')
    # Owner-approved 2026-11-13 additions (bot-policy offline study): rank change
    # alone is not a replacement reason, costs are stated in NAV terms, unknown
    # net benefit is written as 未知, and imprecise marks are labelled.
    assert 'rank change by itself is not a' in SYSTEM
    assert 'round-trip cost' in SYSTEM
    assert '未知' in SYSTEM
    assert 'portfolio value is approximate' in SYSTEM
    # The prompt still formats (schema placeholder intact, no stray braces).
    rendered = SYSTEM.format(schema='{}')
    assert '{schema}' not in rendered and 'FACT DISCIPLINE' in rendered


async def test_prompt_version_is_recorded_in_run_diagnostics(monkeypatch):
    from datetime import UTC, datetime, timedelta
    from unittest.mock import AsyncMock

    from alpha_agent.paper import bot_runner, bot_store
    from alpha_agent.paper.bot_models import BotConfig

    run = {'id': 'one', 'account_id': 1, 'stage': 'queued', 'config_version': 1,
           'config_snapshot': BotConfig().model_dump(), 'context': {}, 'lease_token': 'lease',
           'created_at': datetime.now(UTC), 'expires_at': datetime.now(UTC) + timedelta(minutes=10),
           'llm_calls': 0}
    monkeypatch.setattr(bot_store, 'claim', AsyncMock(return_value=run))
    monkeypatch.setattr(bot_runner, 'market_session', lambda: {'is_open': True})
    context = {'quote_coverage': {}, 'research_age_sessions': 0}
    monkeypatch.setattr(bot_runner, 'build_context', AsyncMock(return_value=context))
    diagnose, release = AsyncMock(), AsyncMock()
    monkeypatch.setattr(bot_store, 'diagnose', diagnose)
    monkeypatch.setattr(bot_store, 'release', release)
    pool = type('Pool', (), {'fetchval': AsyncMock(return_value=1), 'execute': AsyncMock(),
                             'fetchrow': AsyncMock(return_value={'id': 'one', 'status': 'running',
                                                                 'stage': 'deciding'})})()
    await bot_runner.step(pool)
    recorded = diagnose.call_args_list[0].args[2]
    assert recorded['prompt_version'] == bot_runner.PROMPT_VERSION
    release.assert_awaited_once()
