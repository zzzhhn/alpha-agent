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
