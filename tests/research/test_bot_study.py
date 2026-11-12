"""Hand-verifiable fixtures; never touch the production export."""
import numpy as np
import pandas as pd
import pytest

from scripts.research.bot_study import (
    Policy, bootstrap_metrics, evidence_check, fill_cash_delta, numeric_claims,
    policy_grid, rebalance, select_targets, simulate, snapshot_clock, summarize,
)


def test_d_plus_one_close_no_decision_day_profit():
    days = ['2026-06-22', '2026-06-23', '2026-06-24']
    prices = pd.DataFrame({'A': [10., 20., 30.]}, index=days)
    snapshot = {'decision_index': 0, 'ranks': {'tactical': {'A': 1}}, 'eligible': ['A']}
    path = simulate(Policy(n=1, kind='spy'), [snapshot], days, prices,
                    initial_cash=100., fee_bps=0, slippage_bps=0)
    # 1% cash reserve => 4 shares at 20; gain 40 next day, not 100 on D.
    assert path['nav'].tolist() == [100., 100., 140.]
    assert path['returns'][1] == 0


def test_fees_slippage_both_sides_and_cross_term():
    assert fill_cash_delta('buy', 10, 100) == pytest.approx(-1001.5005)
    assert fill_cash_delta('sell', 10, 100) == pytest.approx(998.5005)
    assert fill_cash_delta('buy', 10, 100) + fill_cash_delta('sell', 10, 100) == pytest.approx(-3.)
    cash, held, turn, drag, failure = rebalance(2000., {}, {'A': 100.}, ['A'], cap=1.)
    assert held == {'A': 19}
    assert cash == pytest.approx(2000-19*100*1.0005*1.001)
    assert turn == .95
    assert drag == pytest.approx(19*.15005/2000)
    assert failure is None


def test_hold_band_sells_only_beyond_boundary_and_only_buys_top8():
    p = Policy(n=8, hold_k=12)
    ranks = {'A': 12, 'B': 13, 'C': 1, 'D': 9}
    assert select_targets({'A': 2, 'B': 2}, ranks, p) == ['A', 'C']
    assert select_targets({'A': 2}, {'A': 12, 'D': 9}, p) == ['A']
    assert select_targets({'A': 2}, {'C': 1}, p) == ['C']


def test_hold_band_does_not_rebalance_retained_units():
    cash, held, turnover, _, _ = rebalance(500., {'A': 1}, {'A': 150.}, ['A'], preserve=True)
    assert cash == 500.
    assert held == {'A': 1}
    assert turnover == 0.


def test_evidence_map_missing_wrong_ticker_and_legacy_unknown():
    c = {'evidence_map': {'r1': {'ticker': 'A'}}, 'instruments': [{'instrument_id': '1', 'ticker': 'A'}]}
    d = {'actions': [{'instrument_id': '1', 'evidence_ids': ['r1', 'r2']}]}
    assert evidence_check(c, d)['missing_references'] == 1
    d['actions'][0]['evidence_ids'] = ['r1']
    assert evidence_check(c, d)['missing_references'] == 0
    c['instruments'][0]['ticker'] = 'B'
    assert evidence_check(c, d)['wrong_ticker_actions'] == 1
    assert evidence_check({}, d)['missing_references'] is None


def test_publication_after_close_delays_decision_and_weekend_maps_forward():
    days = ['2026-06-22', '2026-06-23', '2026-06-24']
    closes = [d+'T20:00:00+00:00' for d in days]
    assert snapshot_clock('2026-06-20', '2026-06-20T10:00Z', days, closes) == (0, 1)
    assert snapshot_clock('2026-06-22', '2026-06-22T20:01Z', days, closes) == (1, 2)
    assert snapshot_clock('2026-06-24', '2026-06-24T10:00Z', days, closes) == (None, None)


def test_missing_target_keeps_cash_no_price_based_reranking():
    cash, held, _, _, _ = rebalance(1000., {}, {'A': np.nan, 'B': 10.}, ['A', 'B'])
    assert held == {'B': 25}  # cap .25, missing A never replaced
    assert cash > 700


def test_full_turnover_budget_rejects_instead_of_scaling():
    cash, held, turn, _, failure = rebalance(0., {'A': 10}, {'A': 100., 'B': 100.}, ['B'], cap=1., turnover_cap=1.)
    assert failure == 'turnover_budget_exceeded'
    assert (cash, held, turn) == (0., {'A': 10}, 0.)


def test_numeric_checks_do_not_confuse_score_with_expected_return():
    c = {'recommendations': [{'ticker': 'ABC', 'rank': 3, 'composite_z': .925}], 'account': {}}
    assert numeric_claims(c, 'ABC第3，ABC（0.925）')['mismatches'] == 0
    assert numeric_claims(c, 'ABC第6')['mismatches'] == 1
    assert numeric_claims(c, '综合分差距不足覆盖成本')['score_cost_uncalibrated']


def test_trial_grid_and_paired_bootstrap_reproducible():
    assert len(policy_grid()) == len({p.name for p in policy_grid()}) == 36
    r = np.array([.01, -.01, .02, 0., -.005, .003])
    first = bootstrap_metrics(r, r, r, np.zeros(6), reps=50)
    assert first == bootstrap_metrics(r, r, r, np.zeros(6), reps=50)
    assert first['excess_spy'] == [0., 0.]


def test_missing_holding_is_flagged_not_a_zero_return_observation():
    days = ['2026-06-22', '2026-06-23', '2026-06-24']
    prices = pd.DataFrame({'A': [10., 10., np.nan]}, index=days)
    snap = {'decision_index': 0, 'ranks': {'tactical': {'A': 1}}, 'eligible': ['A']}
    path = simulate(Policy(n=1), [snap], days, prices, initial_cash=100.)
    assert path['missing'].tolist() == [False, False, True]


def test_weekly_cadence_cannot_repeat_within_same_iso_week():
    days = ['2026-06-22', '2026-06-23', '2026-06-24', '2026-06-25']
    prices = pd.DataFrame({'A': [10.]*4, 'B': [10.]*4}, index=days)
    snaps = [{'decision_index': i, 'ranks': {'tactical': {t: 1}}, 'eligible': [t]}
             for i, t in enumerate(['A', 'B', 'A'])]
    path = simulate(Policy(n=1, cadence='weekly'), snaps, days, prices, initial_cash=100.)
    assert path['events'] == 1


def test_incomplete_benchmark_does_not_erase_clean_arm_return():
    days = ['2026-06-22', '2026-06-23', '2026-06-24']
    prices = pd.DataFrame({'A': [10., 10., 11.]}, index=days)
    snap = {'decision_index': 0, 'ranks': {'tactical': {'A': 1}}, 'eligible': ['A']}
    clean = simulate(Policy(n=1), [snap], days, prices, initial_cash=100.)
    broken = {**clean, 'missing': np.array([False, False, True])}
    metrics = summarize(clean, clean, broken, reps=30)
    assert metrics['return'] is not None
    assert metrics['excess_spy'] == 0.
    assert metrics['excess_eligible'] is None
    assert metrics['ci95']['excess_eligible'] is None
    metrics = summarize(broken, clean, clean, reps=30)
    assert metrics['return'] is None
    assert metrics['max_drawdown'] is None
    assert metrics['ci95']['return'] is None
    assert 'diagnostic_carried_marks' in metrics
