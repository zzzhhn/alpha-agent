# tests/paper/test_fill_engine.py
from datetime import date
import pytest
from alpha_agent.paper.fill_engine import (
    LimitExpiry,
    compute_market_fill,
    compute_limit_fill,
    new_avg_cost,
    unrealized_pnl,
    realized_pnl_delta,
)

class TestComputeMarketFill:
    def test_weekend_quote_and_later_session_do_not_substitute_for_t1(self):
        signal = date(2026, 7, 10)
        prices = {date(2026, 7, 11): 185.0, date(2026, 7, 14): 190.0}
        assert compute_market_fill(signal, prices, as_of=date(2026, 7, 14)) is None

    def test_exact_t1_must_be_a_completed_session(self):
        signal = date(2026, 7, 2)
        prices = {date(2026, 7, 3): 99.0, date(2026, 7, 6): 100.0}
        assert compute_market_fill(signal, prices, as_of=signal) is None
        assert compute_market_fill(signal, prices, as_of=date(2026, 7, 6)) == (date(2026, 7, 6), 100.0)

    def test_fills_at_t1_close(self):
        prices = {date(2026, 7, 14): 130.0, date(2026, 7, 15): 132.5}
        result = compute_market_fill(date(2026, 7, 13), prices, as_of=max(prices))
        assert result == (date(2026, 7, 14), 130.0)

    def test_returns_none_when_no_t1_price(self):
        result = compute_market_fill(date(2026, 7, 13), {}, as_of=date(2026, 7, 14))
        assert result is None

    def test_picks_earliest_date_after_signal(self):
        prices = {date(2026, 7, 16): 140.0, date(2026, 7, 14): 130.0}
        result = compute_market_fill(date(2026, 7, 13), prices, as_of=max(prices))
        assert result == (date(2026, 7, 14), 130.0)


class TestComputeLimitFill:
    def test_missing_quotes_do_not_extend_limit_window_across_holiday(self):
        signal = date(2026, 7, 2)
        prices = {date(2026, 7, 3): 99.0, date(2026, 7, 8): 99.0}
        assert compute_limit_fill("buy", 100.0, signal, prices, 2, as_of=date(2026, 7, 6)) is None
        expiry = LimitExpiry((date(2026, 7, 6), date(2026, 7, 7)))
        assert compute_limit_fill("buy", 100.0, signal, prices, 2, as_of=date(2026, 7, 7)) == expiry
        assert compute_limit_fill("buy", 100.0, signal, prices, 2, as_of=date(2026, 7, 8)) == expiry

    def test_three_session_limit_expiry_identifies_missing_quote(self):
        first, second, third = (date(2026, 7, day) for day in (14, 15, 16))
        signal = date(2026, 7, 13)
        prices = {first: 101.0, third: 100.0}  # A touch is not a cross.
        assert compute_limit_fill('buy', 100.0, signal, prices, 3, as_of=second) is None
        expired = compute_limit_fill('buy', 100.0, signal, prices, 3, as_of=third)
        assert expired == LimitExpiry((second,))

    def test_buy_fills_when_close_strictly_below_limit(self):
        prices = {date(2026, 7, 14): 124.99}
        result = compute_limit_fill("buy", 125.0, date(2026, 7, 13), prices, 5, as_of=max(prices))
        assert result == (date(2026, 7, 14), 125.0)

    def test_buy_does_not_fill_when_close_equals_limit(self):
        prices = {date(2026, 7, 14): 125.0}
        result = compute_limit_fill("buy", 125.0, date(2026, 7, 13), prices, 5, as_of=max(prices))
        assert result is None

    def test_sell_fills_when_close_strictly_above_limit(self):
        prices = {date(2026, 7, 14): 125.01}
        result = compute_limit_fill("sell", 125.0, date(2026, 7, 13), prices, 5, as_of=max(prices))
        assert result == (date(2026, 7, 14), 125.0)

    def test_expires_after_n_trading_days(self):
        # The fifth exchange session is Monday (not Saturday).
        prices = {
            date(2026, 7, 14): 126.0,
            date(2026, 7, 15): 126.5,
            date(2026, 7, 16): 127.0,
            date(2026, 7, 17): 127.5,
            date(2026, 7, 20): 128.0,
        }
        result = compute_limit_fill("buy", 125.0, date(2026, 7, 13), prices, 5, as_of=max(prices))
        assert result == LimitExpiry(())

    def test_pending_when_fewer_than_n_days_available(self):
        prices = {date(2026, 7, 14): 126.0, date(2026, 7, 15): 126.5}
        result = compute_limit_fill("buy", 125.0, date(2026, 7, 13), prices, 5, as_of=max(prices))
        assert result is None

    def test_fills_on_first_crossing_day_not_last(self):
        prices = {
            date(2026, 7, 14): 126.0,  # no cross
            date(2026, 7, 15): 124.5,  # cross here
            date(2026, 7, 16): 123.0,
        }
        result = compute_limit_fill("buy", 125.0, date(2026, 7, 13), prices, 5, as_of=max(prices))
        assert result == (date(2026, 7, 15), 125.0)


class TestAvgCost:
    def test_new_position(self):
        assert new_avg_cost(0, 0.0, 100, 150.0) == 150.0

    def test_adds_to_existing(self):
        cost = new_avg_cost(100, 150.0, 50, 160.0)
        assert abs(cost - 153.333333) < 0.001


class TestPnl:
    def test_unrealized_pnl_profit(self):
        assert unrealized_pnl(100, 150.0, 160.0) == pytest.approx(1000.0)

    def test_unrealized_pnl_loss(self):
        assert unrealized_pnl(100, 150.0, 140.0) == pytest.approx(-1000.0)

    def test_realized_pnl_delta(self):
        assert realized_pnl_delta(150.0, 165.0, 50) == pytest.approx(750.0)
