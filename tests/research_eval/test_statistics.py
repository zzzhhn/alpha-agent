"""Hand-computable synthetic statistics and independent numerical references."""
from datetime import date, timedelta
from math import sqrt
from statistics import NormalDist, mean, stdev

import pytest

from alpha_agent.research_eval.statistics import (
    deflated_sharpe, holm, newey_west, non_overlapping,
)


def test_hac_hand_computed_bartlett_lag_one():
    # mean=2.5, gamma0=1.25, gamma1=.3125, LRV=1.5625.
    result = newey_west([1, 2, 3, 4], lag=1)
    assert result.mean == 2.5
    assert result.se == pytest.approx(.625)
    assert result.t == pytest.approx(4)


def test_hac_zero_lag_and_dependence():
    x = [1]*10 + [-1]*10
    iid, hac = newey_west(x, lag=0), newey_west(x, lag=3)
    assert iid.se == pytest.approx(sqrt(1/20))
    assert hac.se > iid.se
    assert hac.t == 0


def test_hac_short_zero_variance_and_bandwidth():
    assert newey_west([]).t is None
    assert newey_west([1, 2]).se is None
    assert newey_west([0]*10).t is None
    assert newey_west([.01]*8).t is None
    assert newey_west(list(range(60)), horizon=20).lag >= 19
    with pytest.raises(ValueError):
        newey_west([1, 2, 3], horizon=5, lag=1)


def test_nonoverlap_preserves_calendar_anchor_across_missing_dates():
    days = [date(2020, 1, 1)+timedelta(days=i) for i in range(7)]
    values = {day: .1 for day in days}
    del values[days[1]]
    blocks = non_overlapping(values, days, 3)
    assert blocks == {days[2]: None, days[5]: pytest.approx(.331)}
    assert non_overlapping(values, days, 3, offset=1)[days[3]] is None
    assert non_overlapping({}, [], 20) == {}
    with pytest.raises(ValueError):
        non_overlapping(values, days, 0)


def test_dsr_one_trial_reduces_to_probabilistic_sharpe():
    # Symmetric returns: skew=0, Pearson kurtosis=1.7, sample SR=mean/stdev.
    x = [-1, 0, 1, 2, 3]
    sr = mean(x)/stdev(x)
    expected = NormalDist().cdf(sr*sqrt(4)/sqrt(1+(1.7-1)*sr*sr/4))
    result = deflated_sharpe(x, trial_sharpes=[sr])
    assert result["benchmark_sharpe"] == 0
    assert result["probability"] == pytest.approx(expected)


def test_dsr_independent_expected_max_reference_and_trial_penalty():
    # Eq 1; reference computed separately by bisection of the erf-based CDF.
    x = [-.01, 0, .01, .02, .03]*10
    result = deflated_sharpe(x, trial_sharpes=[-.1, .1])
    assert result["benchmark_sharpe"] == pytest.approx(.0735045056997513)
    single = deflated_sharpe(x, trial_sharpes=[0])
    assert result["probability"] < single["probability"]


def test_dsr_reports_missing_information_instead_of_fake_significance():
    assert deflated_sharpe([1, 2], trial_sharpes=[0])["reason"] == "short_sample"
    assert deflated_sharpe([0]*5, trial_sharpes=[0])["reason"] == "zero_variance"
    with pytest.raises(ValueError):
        deflated_sharpe([1, 2, 3], trial_sharpes=[])
    with pytest.raises(ValueError):
        deflated_sharpe([1, 2, 3], trial_sharpes=[0], independent_trials=2)


def test_holm_order_monotonicity_ties_and_invalid():
    assert holm([.03, .001, .02]) == pytest.approx((.04, .003, .04))
    assert holm([.02, .02]) == pytest.approx((.04, .04))
    assert holm([]) == ()
    with pytest.raises(ValueError):
        holm([1.1])
