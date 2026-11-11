"""Hand-computed synthetic ledgers, never evidence of market performance.

Small capital and, where stated, widened synthetic caps/short momentum lags
make share-level constraints observable with only three or four securities.
The frozen PROTOCOL itself is never changed.
"""
from dataclasses import replace
from datetime import date, timedelta
from math import isfinite, nan
from types import SimpleNamespace

import pytest

from alpha_agent.research_eval.baselines import replay_baseline, run_historical_diagnostic
from alpha_agent.research_eval.metrics import nav_from_returns
from alpha_agent.research_eval.protocol import PROTOCOL, DateRange


DAYS = tuple(date.fromisoformat(day) for day in (
    "2026-01-27", "2026-01-28", "2026-01-29", "2026-01-30",
    "2026-02-02", "2026-02-03", "2026-02-26", "2026-02-27",
    "2026-03-02", "2026-03-03",
))
TOY = replace(PROTOCOL, baseline_initial_capital=1000)


def replay(prices=None, eligible=None, **kwargs):
    return replay_baseline(
        "ew_monthly", DAYS, ("A", "B", "C"),
        prices if prices is not None else [[3, 4, 6] for _ in DAYS],
        eligible if eligible is not None else [[True] * 3 for _ in DAYS],
        protocol=kwargs.pop("protocol", TOY), **kwargs,
    )


def test_initial_cost_integer_shares_leftover_and_no_terminal_liquidation():
    result = replay(fee_bps=10, slippage_bps=5)
    # $20 per name -> 6*$3 + 5*$4 + 3*$6 = $56, not $60.
    # Cost: 56 * ((1.0005 * 1.001) - 1) = .084028.
    assert result.holdings[DAYS[4]] == {"A": 6, "B": 5, "C": 3}
    assert result.cash[DAYS[4]] == pytest.approx(943.915972)
    assert result.nav[DAYS[4]] == pytest.approx(999.915972)
    assert result.total_costs == pytest.approx(.084028)
    assert result.turnover[DAYS[4]] == pytest.approx(.056)
    assert result.nav[DAYS[3]] == 1000  # hold cash until D+1 close
    assert [r.signal_date for r in result.rebalances] == [DAYS[3], DAYS[7]]
    assert len(result.trades) == 3  # subsequent sub-share deltas truncate to zero
    assert all(t.side == "buy" and t.status == "filled" for t in result.trades)
    assert result.holdings[DAYS[-1]] == result.holdings[DAYS[4]]
    assert result.nav[DAYS[-1]] == pytest.approx(999.915972)
    assert result.protocol_version == PROTOCOL.version
    assert result.protocol_fingerprint == TOY.fingerprint
    assert result.fee_bps == 10 and result.slippage_bps == 5
    reference = nav_from_returns([0], [.056], [0], fee_bps=10,
                                 slippage_bps=5, initial=1000)
    assert result.nav[DAYS[4]] == pytest.approx(reference.nav[-1])


def test_explicit_sells_charge_slipped_fees_on_both_sides():
    eligible = [[True] * 3 if i < 7 else [False] * 3 for i in range(len(DAYS))]
    result = replay(eligible=eligible, fee_bps=10, slippage_bps=5)
    assert result.holdings[DAYS[-1]] == {}
    assert [t.qty for t in result.trades if t.side == "sell"] == [6, 5, 3]
    assert sum(t.cost for t in result.trades if t.side == "sell") == pytest.approx(.083972)
    assert result.total_costs == pytest.approx(.168)
    assert result.nav[DAYS[-1]] == pytest.approx(999.832)


def test_default_two_percent_cap_with_three_names_keeps_cash():
    result = replay([[10] * 3 for _ in DAYS], fee_bps=0)
    assert result.cash[DAYS[4]] == 940
    assert result.holdings[DAYS[4]] == {"A": 2, "B": 2, "C": 2}
    assert result.nav[DAYS[-1]] == 1000


def test_rebalance_scales_all_deltas_at_execution_prices_before_rounding():
    # Widen synthetic position cap to 50% to expose budget scaling with 3 names.
    protocol = replace(TOY, baseline_max_position=.5)
    prices = [[1, 1, 1] if i < 8 else [2, 1, 1] for i in range(len(DAYS))]
    eligible = [[True, True, False] if i < 7 else [False, False, True]
                for i in range(len(DAYS))]
    result = replay(prices, eligible, protocol=protocol, fee_bps=0)
    assert result.holdings[DAYS[4]] == {"A": 500, "B": 500}
    assert result.rebalances[0].turnover == 1
    receipt = result.rebalances[1]
    # Drift NAV=1500, desired sales=1000+500, desired buy=750.
    # 300/2250 = 2/15; truncated quantities sell A66/B66, buy C100.
    assert receipt.nav_before == 1500
    assert receipt.requested_notional == 2250
    assert receipt.scale == pytest.approx(2 / 15)
    assert receipt.gross_notional == 298
    assert receipt.turnover == pytest.approx(298 / 1500)
    assert result.holdings[DAYS[-1]] == {"A": 434, "B": 434, "C": 100}
    assert result.cash[DAYS[-1]] == 98
    assert result.nav[DAYS[-1]] == 1500
    assert receipt.turnover <= .2
    assert receipt.initial_build is False


def test_sells_precede_buys_and_cash_shortfall_trims_ascending_tickers():
    # Synthetic 50% positions, 100% later budget, 1% fee make the rounding
    # and cash reduction visible without 50 securities. Column order is C,B,A.
    protocol = replace(TOY, baseline_max_position=.5, baseline_rebalance_turnover_cap=1)
    eligible = [[False, True, True] if i < 7 else [True, False, True]
                for i in range(len(DAYS))]
    result = replay_baseline("ew_monthly", DAYS, ("C", "B", "A"),
                             [[1] * 3 for _ in DAYS], eligible, protocol=protocol, fee_bps=100)
    # Initial 500+500 costs $1010: trim A10, retain B500, cash $.10.
    assert result.holdings[DAYS[4]] == {"A": 490, "B": 500}
    assert result.cash[DAYS[4]] == pytest.approx(.1)
    # Second pre-cost NAV=990.1. Budget scales 1000.1 requested notional:
    # planned A+4, B-495, C+490. Sell B yields 490.05 + .10 cash.
    # Planned buys cost 498.94: remove A4, then C5 -> buy C485 for 489.85.
    trades = [t for t in result.trades if t.date == DAYS[8]]
    assert [(t.side, t.ticker, t.qty) for t in trades] == [
        ("sell", "B", 495), ("buy", "A", 0), ("buy", "C", 485),
    ]
    assert [(t.status, t.reason, t.requested_qty) for t in trades[1:]] == [
        ("unfilled", "insufficient_cash", 4), ("partial", "insufficient_cash", 490),
    ]
    assert result.cash[DAYS[8]] == pytest.approx(.3)
    assert result.holdings[DAYS[8]] == {"A": 490, "B": 5, "C": 485}
    assert result.nav[DAYS[8]] == pytest.approx(980.3)
    assert all(cash >= 0 for cash in result.cash.values())


def test_missing_execution_leaves_unfilled_exit_and_buy_and_stale_holding():
    prices = [[10] * 3 for _ in DAYS]
    prices[8] = [nan, 10, nan]
    prices[9] = [nan, 10, 10]
    eligible = [[True, True, False] if i < 7 else [False, False, True]
                for i in range(len(DAYS))]
    result = replay(prices, eligible, fee_bps=0)
    missing = [t for t in result.trades if t.reason == "missing_price"]
    assert [(t.ticker, t.side, t.qty, t.requested_qty, t.price) for t in missing] == [
        ("A", "sell", 0, 2, None), ("C", "buy", 0, 2, None),
    ]
    assert all(t.status == "unfilled" and t.cost == 0 for t in missing)
    assert result.holdings[DAYS[8]] == {"A": 2}
    assert result.holdings[DAYS[9]] == {"A": 2}  # C recovers, no retry
    assert result.cash[DAYS[8]] == 980
    assert result.nav[DAYS[8]] == result.nav[DAYS[9]] == 1000
    assert result.turnover[DAYS[8]] == pytest.approx(.02)
    assert result.stale_counts[DAYS[8]] == result.stale_counts[DAYS[9]] == 1
    assert sum(result.stale_counts.values()) == 2
    assert sum(result.missing_counts.values()) == 3


def test_missing_orders_consume_scaling_budget_without_substitution():
    protocol = replace(TOY, baseline_max_position=.5)
    eligible = [[True, True, False] if i < 7 else [False, False, True]
                for i in range(len(DAYS))]
    prices = [[1] * 3 for _ in DAYS]
    prices[8] = [nan, 1, 1]
    result = replay(prices, eligible, protocol=protocol, fee_bps=0)
    # Still 1500 requested -> scale 2/15, including A's missing $500 sale.
    assert result.rebalances[1].requested_notional == 1500
    assert result.rebalances[1].scale == pytest.approx(2 / 15)
    assert result.holdings[DAYS[8]] == {"A": 500, "B": 434, "C": 66}
    assert result.turnover[DAYS[8]] == pytest.approx(.132)


def test_momentum_uses_session_lags_ticker_ties_and_only_endpoint_prices():
    # Synthetic 3/1 lookback and Top2 make a tie cutoff observable in 4 names.
    protocol = replace(TOY, momentum_lookback_sessions=3, momentum_skip_sessions=1,
                       momentum_top_n=2)
    names = ("C", "B", "A", "D")
    prices = [[10] * 4 for _ in DAYS]
    prices[2] = [20, 20, 20, nan]
    prices[3] = [90, 10, nan, 10]  # D close does not enter the 3/1 score
    result = replay_baseline("momentum_12_1", DAYS, names, prices,
                             [[True] * 4 for _ in DAYS], protocol=protocol, fee_bps=0)
    assert result.holdings[DAYS[4]] == {"A": 2, "B": 2}
    assert result.cash[DAYS[4]] == 960  # target cap 2%, no redistribution
    assert [t.ticker for t in result.trades[:2]] == ["A", "B"]
    # EW alone needs a valid D close; A is omitted even though it recovers D+1.
    ew = replay_baseline("ew_monthly", DAYS, names, prices, [[True] * 4 for _ in DAYS],
                         protocol=TOY, fee_bps=0)
    assert ew.holdings[DAYS[4]] == {"B": 2, "C": 2, "D": 2}


def test_frozen_252_21_momentum_warmup_never_trades_before_window():
    days = tuple(date(2025, 5, 24) + timedelta(days=i) for i in range(260))
    # Jan31 is index252; its signal uses index0 and index231, not Jan31 prices.
    assert days[252] == date(2026, 1, 31)
    prices = [[10, 10, 10] for _ in days]
    prices[231] = [20, 10, nan]
    prices[252] = [1, 1000, 10]
    window = DateRange(date(2026, 1, 29), date(2026, 2, 7))
    result = replay_baseline("momentum_12_1", days, ("A", "B", "C"), prices,
                             [[True] * 3 for _ in days], protocol=TOY, fee_bps=0, window=window)
    assert tuple(result.nav) == days[250:]
    assert result.holdings[days[253]] == {"A": 2, "B": 2}
    assert result.cash[days[253]] == 960
    assert len(result.rebalances) == 1
    assert result.rebalances[0].signal_date == days[252]
    assert all(t.date == days[253] for t in result.trades)


def test_eligibility_is_frozen_at_signal_not_execution_or_future():
    eligible = [[True] * 3 for _ in DAYS]
    eligible[3] = [True, False, True]
    eligible[4] = [False, True, True]
    result = replay([[10] * 3 for _ in DAYS], eligible, fee_bps=0)
    assert result.holdings[DAYS[4]] == {"A": 2, "C": 2}


def test_first_successful_build_keeps_initial_budget_after_empty_signal():
    protocol = replace(TOY, baseline_max_position=.5)
    eligible = [[False] * 3 if i < 7 else [True, True, False] for i in range(len(DAYS))]
    result = replay([[1] * 3 for _ in DAYS], eligible, protocol=protocol, fee_bps=0)
    assert result.turnover[DAYS[4]] == 0
    assert result.turnover[DAYS[8]] == 1
    assert all(r.initial_build for r in result.rebalances)


def test_mapping_inputs_and_one_session_have_no_manufactured_entry():
    prices = {day: {"A": 10, "B": 10, "C": 10} for day in DAYS}
    eligible = {day: {"A": True, "B": True, "C": True} for day in DAYS}
    result = replay(prices, eligible, fee_bps=0)
    assert result.cash[DAYS[4]] == 940
    single = replay_baseline("ew_monthly", [DAYS[0]], ["A"], [[10]], [[True]])
    assert single.nav == {DAYS[0]: 1_000_000}
    assert single.trades == single.rebalances == []


@pytest.mark.parametrize("override,match", [
    ({"arm": "other"}, "unknown"),
    ({"sessions": [DAYS[0], DAYS[0]]}, "increasing"),
    ({"tickers": ["A", "A", "B"]}, "unique"),
    ({"adjusted_close": [[10]]}, "shape"),
    ({"eligibility": [[1] * 3 for _ in DAYS]}, "boolean"),
    ({"adjusted_close": [[0, 1, 1] for _ in DAYS]}, "positive"),
    ({"adjusted_close": [[float("inf"), 1, 1] for _ in DAYS]}, "positive"),
    ({"fee_bps": -1}, "invalid"),
    ({"slippage_bps": nan}, "non-finite"),
    ({"window": DateRange(date(2030, 1, 1), date(2030, 2, 1))}, "absent"),
    ({"protocol": replace(TOY, baseline_shares="fractional")}, "unsupported"),
])
def test_rejects_invalid_inputs(override, match):
    args = dict(arm="ew_monthly", sessions=DAYS, tickers=("A", "B", "C"),
                adjusted_close=[[10] * 3 for _ in DAYS], eligibility=[[True] * 3 for _ in DAYS])
    args.update(override)
    with pytest.raises(ValueError, match=match):
        replay_baseline(**args)


def test_diagnostic_reports_missing_fields_and_restores_loader_path(monkeypatch, tmp_path):
    from alpha_agent.factor_engine import factor_backtest

    path = tmp_path / "local.parquet"
    path.write_bytes(b"synthetic placeholder; loader mocked")
    original = factor_backtest.PARQUET_PATH

    def load():
        assert factor_backtest.PARQUET_PATH == path
        return SimpleNamespace(dates=[], tickers=[], close=[], is_member=None)

    monkeypatch.setattr(factor_backtest, "_load_panel", SimpleNamespace(__wrapped__=load))
    result = run_historical_diagnostic(path)
    assert result["label"] == "historical_diagnostic_not_forward_evidence"
    assert result["status"] == "unavailable"
    assert result["missing_fields"] == ["is_member"]
    assert factor_backtest.PARQUET_PATH == original


def test_diagnostic_missing_bundle_never_falls_back_or_fetches(tmp_path):
    result = run_historical_diagnostic(tmp_path / "missing.parquet")
    assert result["status"] == "unavailable"
    assert "missing" in result["reason"]


def test_diagnostic_summary_with_mock_local_panel(monkeypatch, tmp_path):
    import exchange_calendars as xcals

    from alpha_agent.data import membership
    from alpha_agent.factor_engine import factor_backtest

    window = PROTOCOL.historical_test
    calendar = xcals.get_calendar("XNYS", start="2025-01-01", end="2026-10-30")
    days = calendar.sessions_in_range("2025-01-02", window.end)
    panel = SimpleNamespace(dates=[day.date().isoformat() for day in days], tickers=("A", "B", "C"),
                            close=[[10] * 3 for _ in days], is_member=[[True] * 3 for _ in days])
    path = tmp_path / "panel.parquet"
    path.write_bytes(b"synthetic placeholder; loader mocked")
    csv = tmp_path / "members.csv"
    csv.write_text("synthetic membership")
    monkeypatch.setattr(membership, "_DEFAULT_CSV", csv)
    monkeypatch.setattr(factor_backtest, "_load_panel", SimpleNamespace(__wrapped__=lambda: panel))
    summary = run_historical_diagnostic(path)
    assert summary["label"] == "historical_diagnostic_not_forward_evidence"
    assert summary["status"] == "complete"
    assert summary["sessions"] == 148
    assert len(summary["price_sha256"]) == len(summary["membership_sha256"]) == 64
    for arm in summary["arms"].values():
        # First build: $60,000 reference notional, $60 fee. Constant closes
        # leave sub-share target differences, so later monthly trades are zero.
        assert arm["final_nav"] == 999940
        assert arm["total_return"] == pytest.approx(-.00006)
        assert arm["total_cost"] == 60
        assert arm["rebalance_count"] == 6
        assert arm["stale_stock_days"] == arm["missing_price_cells"] == 0
        assert isfinite(arm["final_nav"])


def test_diagnostic_rejects_missing_historical_sessions(monkeypatch, tmp_path):
    from alpha_agent.factor_engine import factor_backtest

    path = tmp_path / "panel.parquet"
    path.write_bytes(b"synthetic placeholder; loader mocked")
    panel = SimpleNamespace(dates=["2026-04-01", "2026-10-30"], tickers=("A",),
                            close=[[10], [10]], is_member=[[True], [True]])
    monkeypatch.setattr(factor_backtest, "_load_panel", SimpleNamespace(__wrapped__=lambda: panel))
    summary = run_historical_diagnostic(path)
    assert summary["status"] == "unavailable"
    assert summary["reason"] == "incomplete historical session calendar"
