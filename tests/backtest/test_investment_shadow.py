from datetime import date

import pytest

from alpha_agent.backtest.investment_shadow import replay_targets


def test_turnover_replay_keeps_costs_and_monthly_hold_distinct():
    days = [date(2026, 8, 3), date(2026, 8, 10), date(2026, 8, 11)]
    prices = {(day, ticker): 100.0 for day in days for ticker in ("AAA", "BBB")}
    prices[days[-1], "AAA"] = 110.0
    targets = {days[0]: {"AAA": 1.0}, days[1]: {"BBB": 1.0}}
    recorded = replay_targets(days, targets, prices, mode="recorded", cost_bps=10)
    monthly = replay_targets(days, targets, prices, mode="monthly", cost_bps=10)
    assert recorded["net_return"] < 0  # flat prices still incur costs
    assert monthly["net_return"] == pytest.approx(1.1 / 1.001 - 1)
    assert monthly["trade_batches"] == 1
    assert monthly["two_way_turnover"] < recorded["two_way_turnover"]
    del prices[days[1], "AAA"]
    assert replay_targets(days, targets, prices, mode="monthly", cost_bps=10)["status"] == "missing_prices"
