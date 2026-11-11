"""Display-only Picks contracts over immutable complete populations."""
from copy import deepcopy
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock

import pytest

from alpha_agent.api.routes.picks import (
    PicksResponse, _build_canonical_view, _recommendation_changes, snapshot_rank_scores,
)
from alpha_agent.fusion.policy import get_policy


@pytest.mark.parametrize(('values', 'expected', 'population'), [
    ({'A': 0., 'B': 1., 'C': 1., 'D': 2.}, {'A': 0, 'B': 50, 'C': 50, 'D': 100}, 4),
    ({'A': 0., 'B': 1., 'C': 1., 'D': 2., 'E': 3.}, {'A': 0, 'B': 38, 'C': 38, 'D': 75, 'E': 100}, 5),
    ({'A': 1., 'B': 1.}, {'A': 50, 'B': 50}, 2),
    ({'A': 1., 'B': None, 'C': float('nan'), 'D': float('inf')}, dict.fromkeys('ABCD'), 1),
    ({'A': None}, {'A': None}, 0),
    ({}, {}, 0),
])
def test_rank_ties_rounding_and_missing(values, expected, population):
    assert snapshot_rank_scores(values) == (expected, population)


def snapshot(ticker, score, rank, *, strategic=None, eligible=True, in_universe=True):
    payload = dict(ticker=ticker, composite_score=score, rating='OW', confidence=.5,
                   as_of='2026-11-10T22:00:00+00:00', top_drivers=[], top_drags=[],
                   price_date='2026-11-10')
    if strategic is not None:
        payload['_mode_payloads'] = {'long': {
            **payload, 'composite_score': strategic, 'sleeve': 'strategic',
            'policy_id': get_policy('strategic').policy_id, 'policy_rank': rank,
        }}
    return dict(ticker=ticker, composite_z=score, rank=rank, eligible=eligible,
                in_universe=in_universe, tier='OW', user_visible_payload_json=payload)


async def canonical(monkeypatch, rows, *, mode='short', side='long', limit=50):
    from alpha_agent.storage import product_ledger
    run = dict(id=10, scheduled_for_date=date(2026, 11, 10), run_type='daily_close',
               finished_at=datetime(2026, 11, 10, 22, tzinfo=UTC), data_asof=None,
               input_data_cutoff=None, weight_policy_id='same-policy', health_json={'passed': True})
    monkeypatch.setattr(product_ledger, 'get_latest_canonical_run', AsyncMock(return_value=run))
    monkeypatch.setattr(product_ledger, 'get_run_snapshots', AsyncMock(return_value=rows))
    return await _build_canonical_view(AsyncMock(fetchrow=AsyncMock(return_value=None)),
                                     mode=mode, side=side, limit=limit)


async def test_canonical_full_population_side_limit_pagination_invariance(monkeypatch):
    rows = [snapshot('AAA', 3., 1), snapshot('BBB', 1., 2), snapshot('CCC', 1., 3),
            snapshot('DDD', -2., 4), snapshot('EEE', 2., None),
            snapshot('OUT', 100., 5, eligible=False), snapshot('OFF', 200., 6, in_universe=False)]
    before = deepcopy(rows)
    all_cards = await canonical(monkeypatch, rows)
    expected = {c.ticker: c.rank_score for c in all_cards.picks}
    assert expected == {'AAA': 100, 'BBB': 38, 'CCC': 38, 'DDD': 0}
    assert all_cards.rank_score_method.population == 5  # includes eligible unranked EEE
    for side in ['long', 'short']:
        for limit in [1, 2, 50]:
            result = await canonical(monkeypatch, rows, side=side, limit=limit)
            assert result.rank_score_method.population == 5
            assert all(c.rank_score == expected[c.ticker] for c in result.picks)
            scores = [c.rank_score for c in result.picks]
            assert scores == sorted(scores, reverse=side == 'long')
            # Client pagination only slices the response, never re-scores it.
            assert [c.rank_score for c in result.picks[1:2]] == scores[1:2]
    assert rows == before
    assert all_cards.picks[0].dimension_scores is None  # old snapshot is not regraded


async def test_strategic_uses_matching_policy_complete_population(monkeypatch):
    rows = [snapshot('AAA', 100., 1, strategic=-2.), snapshot('BBB', 0., 2, strategic=2.),
            snapshot('CCC', -100., 3, strategic=0.), snapshot('OLD', 200., 4, strategic=99.)]
    rows[-1]['user_visible_payload_json']['_mode_payloads']['long']['policy_id'] = 'older-policy'
    result = await canonical(monkeypatch, rows, mode='long', limit=1)
    assert [(c.ticker, c.rank_score) for c in result.picks] == [('BBB', 100)]
    assert result.rank_score_method.population == 3
    assert result.rank_score_method.sleeve == 'strategic'
    shorts = await canonical(monkeypatch, rows, mode='long', side='short', limit=1)
    assert [(c.ticker, c.rank_score) for c in shorts.picks] == [('AAA', 0)]


async def test_canonical_invalid_composites_remain_unknown(monkeypatch):
    rows = [snapshot('AAA', 1., 1), snapshot('BBB', float('nan'), 2), snapshot('CCC', None, 3)]
    result = await canonical(monkeypatch, rows)
    assert result.rank_score_method.status == 'insufficient_population'
    assert all(c.rank_score is None for c in result.picks)
    assert result.picks[-1].composite_score is None
    result.model_dump_json()  # no non-finite JSON output


def test_exploratory_method_never_claims_a_population():
    result = PicksResponse(picks=[], as_of=None, stale=False)
    assert result.rank_score_method.status == 'unavailable_exploratory_view'
    assert result.rank_score_method.population == 0


def test_changes_scope_dates_and_no_fabricated_previous():
    current = [snapshot('AAA', 2., 1), snapshot('OUT', 3., 51)]
    previous = deepcopy(current)
    previous[0]['user_visible_payload_json']['rating'] = 'BUY'
    previous[1]['user_visible_payload_json']['rating'] = 'SELL'
    kwargs = dict(mode='short', policy_id='same-policy', prior_run_id=9,
                  current_market_date='2026-11-10', prior_market_date='2026-11-09')
    changes = _recommendation_changes(current, previous, **kwargs)
    assert [c.ticker for c in changes.tier_changes] == ['AAA']
    assert changes.current_market_date == '2026-11-10'
    assert changes.prior_market_date == '2026-11-09'
    missing = _recommendation_changes(current, [], **kwargs)
    assert missing.available is False and not missing.tier_changes
