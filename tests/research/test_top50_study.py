"""Hand-checkable contracts; no private data, IO, DB, or network."""

import numpy as np
import pandas as pd
import pytest

from scripts.research.top50_study import (
    cohort_rebalance,
    forward_returns,
    mean_stats,
    pit_quality,
    rank_ic,
    round_trip_net,
    trial_log,
    xnys_sessions,
)
from alpha_agent.research_eval.statistics import newey_west


def test_d1_entry_uses_exchange_sessions_including_holiday():
    days, _ = xnys_sessions("2026-07-02", "2026-07-08")
    assert days.strftime("%Y-%m-%d").tolist() == [
        "2026-07-02",
        "2026-07-06",
        "2026-07-07",
        "2026-07-08",
    ]
    p = pd.DataFrame({"A": [100, 110, 121, 133.1]}, index=days)
    r = forward_returns(p, 1)
    assert r.iloc[0, 0] == pytest.approx(0.1)  # 121/110, not 110/100 or 121/100
    assert r.iloc[1, 0] == pytest.approx(0.1)
    assert r.iloc[2:, 0].isna().all()
    assert forward_returns(p, 1, block_end=days[1]).A.isna().all()


def test_missing_session_price_never_becomes_next_available_entry():
    days = pd.bdate_range("2026-01-05", periods=5)
    p = pd.DataFrame({"A": [100, np.nan, 110, 121, 133.1]}, index=days)
    assert np.isnan(forward_returns(p, 1).iloc[0, 0])
    assert forward_returns(p, 1).iloc[1, 0] == pytest.approx(0.1)


def test_suspect_move_and_para_identity_are_separate_sensitivities():
    days = pd.bdate_range("2026-01-05", periods=4)
    p = pd.DataFrame({"A": [100, 100, 150, 150], "PARA": [100, 100, 100, 100]}, index=days)
    assert np.isnan(forward_returns(p, 1).A.iloc[0])
    assert forward_returns(p, 1, clean=False).A.iloc[0] == pytest.approx(0.5)
    assert forward_returns(p, 1, clean=False).PARA.isna().all()


def test_two_sided_cost_uses_exit_notional_and_keeps_losses():
    assert round_trip_net(0.1, 10) == pytest.approx(0.1 - 0.001 - 0.0011)
    assert round_trip_net(-0.1, 10) == pytest.approx(-0.1 - 0.001 - 0.0009)
    assert round_trip_net(0, 30) == pytest.approx(-0.006)


def test_hac_complete_matches_frozen_helper_and_overlap_lag_floor():
    days = pd.bdate_range("2026-01-05", periods=80)
    x = np.sin(np.arange(80) / 6) / 100 + 0.001
    expected = newey_west(x.tolist(), horizon=20)
    actual = mean_stats(pd.Series(x, index=days), days, 20)
    assert actual["hac_lag"] == 19
    assert actual["hac_se"] == pytest.approx(expected.se)
    assert actual["hac_t"] == pytest.approx(expected.t)
    assert actual["nonoverlap_offset0_n"] == 4
    assert actual["effective_n_hac_approx"] < 80


def test_hac_gap_keeps_calendar_lag_and_nonoverlap_anchors():
    days = pd.bdate_range("2026-01-05", periods=8)
    s = pd.Series([1.0, -1.0, 1.0, -1.0], index=days[[0, 2, 4, 6]])
    result = mean_stats(s, days, 2)
    # n=4, default L=1. All lag1 covariance terms absent, LRV=1, SE=.5.
    assert result["hac_se"] == pytest.approx(0.5)
    assert result["nonoverlap_offsets"][0]["n"] == 4
    assert result["nonoverlap_offsets"][1]["n"] == 0
    assert result["gapped"]
    assert mean_stats(s.iloc[:2], days, 20)["hac_t"] is None


def test_pit_filing_date_not_report_period_and_200_day_expiry():
    filings = pd.DataFrame(
        {
            "ticker": ["A", "A"],
            "filing_date": ["2025-01-03", "2025-01-07"],
            "report_period": ["2024-09-30", "2024-12-31"],
            "gross_profit": [10.0, 30.0],
            "assets": [100.0, 100.0],
        }
    )
    days = pd.DatetimeIndex(["2025-01-02", "2025-01-03", "2025-01-06", "2025-01-07", "2025-08-01"])
    q = pit_quality(filings, days, ["A", "B"])
    assert np.isnan(q.A.iloc[0])
    assert q.A.iloc[1:4].tolist() == [0.1, 0.1, 0.3]
    assert np.isnan(q.A.iloc[4])
    assert q.B.isna().all()


def test_ic_direction_and_constant_signal_not_zero_evidence():
    r = pd.Series([0.3, 0.2, 0.1])
    rank = pd.Series([1.0, 2.0, 3.0])
    assert rank_ic(rank, r, minimum=3) == pytest.approx(-1)
    assert rank_ic(-rank, r, minimum=3) == pytest.approx(1)
    assert np.isnan(rank_ic(pd.Series([0.0, 0.0, 0.0]), r, minimum=3))


def test_nonoverlap_rebalance_drift_cost_and_cash_cap():
    days = pd.bdate_range("2026-01-05", periods=5)
    names = [f"S{i:03}" for i in range(250)]
    scores = pd.DataFrame(np.tile(np.arange(250), (5, 1)), index=days, columns=names)
    returns = scores * 0 + 0.1
    member = scores.notna()
    out = cohort_rebalance(scores, returns, member, days[:1], 5, 10)
    # 50 stocks at 2%, initial buy=1, terminal sell=1.1.
    assert out["top_net"]["mean"] == pytest.approx(0.1 - 0.0021)
    assert out["mean_gross_turnover"] == pytest.approx(2.1)
    assert out["excess"]["mean"] == pytest.approx(0, abs=1e-14)


def test_registry_keeps_unavailable_variants_in_search_count():
    trials = trial_log()
    assert len(trials) == 111
    assert sum(t["family"] == "Q3" for t in trials) == 12
    assert any(t["variant"] == "coverage_ge_0.8" for t in trials)


def test_missing_selected_label_does_not_replace_it_with_next_rank():
    days = pd.bdate_range("2026-01-05", periods=3)
    names = [f"S{i:03}" for i in range(250)]
    scores = pd.DataFrame(np.tile(np.arange(250), (3, 1)), index=days, columns=names)
    returns = scores * 0 + 0.1
    returns.loc[days[0], names[-1]] = np.nan
    result = cohort_rebalance(scores, returns, scores.notna(), days[:1], 5, 10)
    assert result["expected_cohorts"] == 1
    assert result["top_net"]["n"] == 0
    assert result["complete_paired_cohorts"] == 0
