from datetime import UTC, datetime

import pandas as pd
import pytest

from alpha_agent.paper import intraday
from alpha_agent.paper.intraday import fetch_bars, select_fill
from alpha_agent.paper.market_clock import as_utc, market_session, target_slot_times


def stamp(time: str) -> str:
    return f"2026-11-02T{time}+00:00"


def bar(start="14:32:00", end="14:33:00", price=100, **overrides):
    return {
        "start": stamp(start), "end": stamp(end),
        "open": price, "high": price + 1, "low": price - 1, "close": price,
        "volume": 1000, "source": "fixture:raw", "fetched_at": stamp("14:34:00"),
        "price_basis": "raw_unadjusted", "dividends": 0, "stock_splits": 0,
        **overrides,
    }


def fill(bars, **overrides):
    kwargs = {
        "side": "buy", "accepted_at": stamp("14:31:30"),
        "expires_at": stamp("14:40:00"), "bars": bars, "now": stamp("14:35:00"),
    }
    return select_fill(**(kwargs | overrides))


def test_no_pre_decision_or_same_start_fill():
    stale = bar("14:31:00", "14:32:00")
    assert fill([stale])["status"] == "pending"
    assert fill([bar()], accepted_at=stamp("14:32:00"))["status"] == "pending"


def test_bar_must_be_complete_and_fetched_after_completion():
    assert fill([bar()], now=stamp("14:32:50"))["status"] == "pending"
    partial = bar(fetched_at=stamp("14:32:50"))
    assert fill([partial])["reason"] == "awaiting_complete_bar"
    assert fill([bar(fetched_at=stamp("14:36:00"))])["status"] == "pending"


def test_earliest_not_best_bar_and_full_execution_evidence():
    result = fill([bar("14:33:00", "14:34:00", price=90), bar()])
    assert result["status"] == "filled"
    assert result["reference_price"] == 100
    assert result["fill_price"] == pytest.approx(100.05)
    assert result["bar"]["start"] == stamp("14:32:00")
    assert as_utc(result["confirmed_at"]) > as_utc(result["filled_at"])
    assert result["execution_model"] == "intraday_next_bar_v1"
    assert fill([bar()], side="sell")["fill_price"] == pytest.approx(99.95)


@pytest.mark.parametrize("cancel_at", ["14:31:45", "14:32:00"])
def test_cancel_at_or_before_bar_wins(cancel_at):
    assert fill([bar()], cancel_requested_at=stamp(cancel_at))["status"] == "cancelled"


def test_late_cancel_cannot_erase_fill_even_when_data_arrived_later():
    result = fill([bar()], cancel_requested_at=stamp("14:32:30"))
    assert result["status"] == "filled"
    assert result["bar"]["fetched_at"] > stamp("14:32:30")


def test_cancel_after_possible_execution_waits_for_data():
    result = fill([], cancel_requested_at=stamp("14:32:30"))
    assert result["status"] == "pending"
    assert result["reason"] == "cancel_awaiting_market_data"
    assert fill([], cancel_requested_at=stamp("14:31:45"))["status"] == "cancelled"


def test_expiry_releases_missing_data_but_preserves_prior_fill():
    assert fill([], now=stamp("14:40:00"))["status"] == "expired"
    assert fill([bar()], now=stamp("14:41:00"))["status"] == "filled"
    assert fill([bar()], expires_at=stamp("14:32:30"))["status"] == "expired"


def test_expiration_precedes_a_later_cancellation_before_first_minute():
    result = fill([], expires_at=stamp("14:31:40"), cancel_requested_at=stamp("14:31:50"))
    assert result["status"] == "expired"


def test_shortened_session_forbids_fill_after_official_close():
    result = select_fill(
        "buy", "2026-11-27T17:59:10Z", "2026-11-27T21:00:00Z", [{
            **bar(), "start": "2026-11-27T18:00:00Z", "end": "2026-11-27T18:01:00Z",
            "fetched_at": "2026-11-27T18:02:00Z",
        }], "2026-11-27T18:03:00Z",
    )
    assert result["status"] == "expired"


def test_no_next_session_or_after_hours_execution():
    next_day = bar(start="14:32:00", end="14:33:00")
    next_day = {key: value.replace("2026-11-02", "2026-11-03") if key in
                {"start", "end", "fetched_at"} else value for key, value in next_day.items()}
    result = fill([next_day], now="2026-11-03T15:00:00+00:00",
                  expires_at="2026-11-03T21:00:00+00:00")
    assert result["status"] == "expired"
    assert fill([bar()], accepted_at=stamp("14:00:00"))["reason"] == "accepted_outside_regular_session"
    assert fill([bar("21:00:00", "21:01:00")], now=stamp("21:03:00"),
                expires_at=stamp("21:05:00"))["status"] == "expired"


@pytest.mark.parametrize("bad", [0, -1, float("inf"), float("nan"), None])
def test_invalid_first_price_does_not_skip_to_later_bar(bad):
    result = fill([bar(open=bad), bar("14:33:00", "14:34:00", price=90)])
    assert result["status"] == "pending"
    assert result["reason"] == "invalid_ohlc"


def test_invalid_price_range_and_adjusted_prices_are_blocked():
    assert fill([bar(high=95)])["reason"] == "invalid_ohlc_range"
    assert fill([bar(price_basis="adjusted")])["reason"] == "raw_price_evidence_required"


@pytest.mark.parametrize("metadata", [
    {"dividends": 0.5}, {"stock_splits": 2}, {"corporate_actions_known": False},
    {"corporate_actions": [{"at": stamp("14:30:00"), "stock_splits": 2}]},
])
def test_corporate_actions_need_reconciliation(metadata):
    result = fill([bar(**metadata)])
    assert result["status"] == "pending"
    assert result["reason"] == "corporate_action_requires_reconciliation"


def test_naive_timestamps_and_invalid_controls_are_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        market_session(datetime(2026, 11, 2, 15))
    with pytest.raises(ValueError, match="timezone-aware"):
        fill([], accepted_at=datetime(2026, 11, 2, 14, 31))
    with pytest.raises(ValueError, match="slippage"):
        fill([], slippage_bps=float("nan"))
    with pytest.raises(ValueError, match="side"):
        fill([], side="short")


def test_halfday_and_dst_slot_times():
    halfday = market_session("2026-11-27T17:00:00Z")
    assert halfday["close_at"] == "2026-11-27T18:00:00+00:00"
    assert halfday["is_open"]
    slots = target_slot_times("2026-11-27T17:00:00Z")
    assert slots["close_before"] == "2026-11-27T17:30:00+00:00"
    assert target_slot_times("2026-10-30T15:00:00Z")["open_after"] == "2026-10-30T14:00:00+00:00"
    assert target_slot_times("2026-11-02T15:00:00Z")["open_after"] == "2026-11-02T15:00:00+00:00"
    assert target_slot_times("2026-03-06T15:00:00Z")["open_after"] == "2026-03-06T15:00:00+00:00"
    assert target_slot_times("2026-03-09T15:00:00Z")["open_after"] == "2026-03-09T14:00:00+00:00"


def test_weekend_holiday_close_and_exchange_date_not_utc_date():
    weekend = market_session("2026-11-01T16:00:00Z")
    assert not weekend["is_open"] and weekend["session_date"] == "2026-11-02"
    assert weekend["next_open_at"] == "2026-11-02T14:30:00+00:00"
    assert market_session("2026-11-26T16:00:00Z")["session_date"] == "2026-11-27"
    assert not market_session("2026-11-02T21:00:00Z")["is_open"]
    assert market_session("2026-11-03T01:00:00Z")["session_date"] == "2026-11-02"
    assert market_session("2026-11-02T15:00:00Z")["next_open_at"] == "2026-11-03T14:30:00+00:00"
    with pytest.raises(ValueError):
        target_slot_times("2026-11-27T17:00:00Z", close_offset=210)


@pytest.mark.asyncio
async def test_bounded_raw_fetch_filters_old_data_and_preserves_session_actions(monkeypatch):
    frame = pd.DataFrame({
        "Open": [100, 100, 101], "High": [101, 101, 102], "Low": [99, 99, 100],
        "Close": [100, 100, 101], "Volume": [10, 20, 30],
        "Dividends": [0, 0.5, 0], "Stock Splits": [0, 0, 0],
    }, index=pd.to_datetime([
        "2026-10-30T19:59:00Z", "2026-11-02T14:30:00Z", "2026-11-02T14:31:00Z",
    ]))
    monkeypatch.setattr(intraday, "_fetch_history", lambda symbol: frame)
    result = await fetch_bars("spy", now=stamp("14:35:00"))
    assert len(result) == 2
    assert result[0]["open"] == 100
    assert result[0]["price_basis"] == "raw_unadjusted"
    assert result[1]["corporate_actions"][0]["dividends"] == 0.5
    assert as_utc(result[0]["fetched_at"]).tzinfo == UTC
    assert await fetch_bars("SPY", now="2026-11-03T14:35:00Z") == []


@pytest.mark.asyncio
async def test_fetch_is_bounded_and_does_not_persist_or_call_for_invalid_symbol(monkeypatch):
    frame = pd.DataFrame({
        "Open": [100] * 2000, "High": [101] * 2000, "Low": [99] * 2000,
        "Close": [100] * 2000, "Volume": [20] * 2000,
        "Dividends": [0] * 2000, "Stock Splits": [0] * 2000,
    }, index=pd.date_range("2026-11-02T00:00:00Z", periods=2000, freq="min"))
    calls = []

    def history(symbol):
        calls.append(symbol)
        return frame

    monkeypatch.setattr(intraday, "_fetch_history", history)
    result = await fetch_bars("SPY", now=stamp("21:05:00"))
    assert len(result) == intraday.MAX_BARS
    assert calls == ["SPY"]
    with pytest.raises(ValueError, match="ticker"):
        await fetch_bars("SPY AAPL")
    assert calls == ["SPY"]


def test_provider_requests_unadjusted_minute_data(monkeypatch):
    import yfinance as yf

    seen = {}

    class FakeTicker:
        def __init__(self, symbol):
            seen["symbol"] = symbol

        def history(self, **kwargs):
            seen.update(kwargs)
            return pd.DataFrame()

    monkeypatch.setattr(yf, "Ticker", FakeTicker)
    intraday._fetch_history("SPY")
    assert seen["symbol"] == "SPY" and seen["period"] == "1d" and seen["interval"] == "1m"
    assert seen["auto_adjust"] is False and seen["back_adjust"] is False
    assert seen["actions"] is True and seen["prepost"] is False
