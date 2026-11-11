"""Entirely synthetic fixtures; no market-performance evidence."""
from datetime import date, timedelta
from math import nan

import pytest

from alpha_agent.research_eval.metrics import (
    annualized_vol, common_dates, excess_returns, exposure,
    matched_summary, max_drawdown, nav_from_returns,
)


def days(n):
    return [date(2020, 1, 1) + timedelta(days=i) for i in range(n)]


def test_global_intersection_preserves_missingness_and_refuses_path():
    a, b, c = days(3)
    aligned = common_dates({"book": {a: .1, b: -.2, c: .3},
                            "SPY": {a: .1, c: -.1},
                            "bot": {a: .0, b: .0, c: nan}}, [a, b, c])
    assert aligned.dates == (a,)
    assert aligned.values["book"] == (.1,)
    assert aligned.coverage == pytest.approx(1/3)
    assert aligned.missing["SPY"] == (b,)
    assert aligned.missing["bot"] == (c,)
    assert matched_summary(aligned, "book", "SPY")["metrics"] is None


def test_matched_cumulative_excess_is_not_compound_of_return_differences():
    a, b = days(2)
    aligned = common_dates({"a": {a: .1, b: -.1}, "SPY": {a: .02, b: .03}}, [a, b])
    metrics = matched_summary(aligned, "a", "SPY")["metrics"]
    assert metrics["net_return"] == pytest.approx(-.01)
    assert metrics["excess_return_pp"] == pytest.approx(-.0606)
    assert metrics["max_drawdown"] == pytest.approx(-.1)


def test_costs_on_both_sides_with_explicit_entry_and_exit():
    path = nav_from_returns([0, .1, 0], [1, 0, 0], [0, 0, 1], fee_bps=10)
    assert path.nav == pytest.approx([100, 99.9, 109.89, 109.78011])
    assert path.gross_nav[-1] == pytest.approx(110)
    assert path.traded_weight == (1, 0, 1)
    assert path.total_turnover == 2
    assert path.cost_drag == pytest.approx(.0021989)
    assert max_drawdown(path.nav[:2]) == pytest.approx(-.001)


def test_fee_on_slipped_notional():
    path = nav_from_returns([0, 0], [1, 0], [0, 1], fee_bps=10, slippage_bps=5)
    assert path.cost_rates == pytest.approx([.0015005, .0014995])


def test_no_invented_exit_costs_and_empty_path():
    path = nav_from_returns([0], [1], [0], fee_bps=10)
    assert path.nav[-1] == pytest.approx(99.9)
    assert nav_from_returns([], [], [], fee_bps=0).nav == (100,)
    assert max_drawdown([]) is None
    assert annualized_vol([]) is None
    assert annualized_vol([.1]) is None
    assert annualized_vol([0, 0]) == 0
    assert common_dates({"a": {}}, []).coverage is None


@pytest.mark.parametrize("returns,buys,sells,fee", [
    ([.1], [], [], 10), ([nan], [0], [0], 10),
    ([0], [-1], [0], 10), ([-1], [1], [0], 10), ([0], [0], [0], -1),
])
def test_invalid_cost_inputs(returns, buys, sells, fee):
    with pytest.raises(ValueError):
        nav_from_returns(returns, buys, sells, fee_bps=fee)


def test_bankruptcy_and_bad_alignment():
    assert max_drawdown([100, 0]) == -1
    with pytest.raises(ValueError):
        nav_from_returns([-1, .1], [0, 0], [0, 0], fee_bps=0)
    with pytest.raises(ValueError):
        excess_returns([0], [])
    with pytest.raises(ValueError):
        common_dates({"a": {}}, [*days(2), days(1)[0]])
    with pytest.raises(ValueError):
        common_dates({}, days(2))


def test_cash_exposure_and_concentration():
    assert exposure([])["effective_positions"] is None
    result = exposure([.2, .2])
    assert result["cash_weight"] == pytest.approx(.6)
    assert result["invested_hhi"] == pytest.approx(.5)
    assert result["effective_positions"] == pytest.approx(2)
    with pytest.raises(ValueError):
        exposure([.8, .8])
