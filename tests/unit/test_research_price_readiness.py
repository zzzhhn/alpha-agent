from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

import pytest

from alpha_agent.data.research_refresh import research_price_readiness
from scripts.ensure_research_prices import ensure_prices


@pytest.mark.parametrize("missing,spy,ready", [(0, True, True), (2, True, True), (3, True, False), (0, False, False)])
async def test_readiness_uses_current_session_coverage_and_benchmark(monkeypatch, missing, spy, ready):
    names = [f"T{i}" for i in range(40)]
    monkeypatch.setattr("alpha_agent.data.research_refresh.get_priority_universe", AsyncMock(return_value=names))
    pool = AsyncMock()
    async def fetch(sql, *args):
        if "daily_prices" in sql:
            assert args[0].isoformat() == "2026-11-05"
            return [{"ticker": t} for t in names[missing:] + (["SPY"] if spy else [])]
        return []
    pool.fetch.side_effect = fetch
    result = await research_price_readiness(pool, now=datetime(2026, 11, 6, 7, tzinfo=UTC))
    assert result["ready"] is ready
    assert result["missing_count"] == missing
    assert result["price_universe_count"] == 41
    pool.execute.assert_not_called()


def test_fresh_prices_skip_provider_requests():
    request = Mock(return_value={"ok": True, "ready": True})
    capacity = Mock()
    assert ensure_prices(request, capacity)["ready"]
    request.assert_called_once_with("research_readiness")
    capacity.assert_not_called()


def test_recovery_waits_for_actual_coverage_not_processed_rows():
    stale = {"ok": True, "ready": False, "price_universe_count": 76}
    request = Mock(side_effect=[stale, {"updated": 375}, {"updated": 5}, stale.copy()])
    capacity = Mock(return_value={"ready": True})
    result = ensure_prices(request, capacity)
    assert not result["ready"]
    assert result["reason"] == "awaiting_current_market_prices"
    assert request.call_args_list[1].args == ("daily_prices?limit=75&offset=0&period=5d",)
    assert request.call_args_list[2].args == ("daily_prices?limit=75&offset=75&period=5d",)
    assert capacity.call_count == 2


def test_recovery_stops_before_write_when_capacity_pauses():
    request = Mock(return_value={"ok": True, "ready": False, "price_universe_count": 76})
    result = ensure_prices(request, lambda: {"ready": False, "expected_pause": True})
    assert result["reason"] == "service_or_storage_paused"
    request.assert_called_once_with("research_readiness")


def test_recovery_does_not_hide_auth_or_code_errors_as_data_pause():
    request = Mock(return_value={"ok": True, "ready": False, "price_universe_count": 76})
    with pytest.raises(RuntimeError, match="unexpectedly"):
        ensure_prices(request, lambda: {"ready": False, "expected_pause": False})


async def test_daily_prices_filters_nonfinite_and_unfinished_candles(monkeypatch):
    import pandas as pd
    from api.cron.daily_prices import handler

    pool = AsyncMock()
    pool.fetch.return_value = [{"ticker": "A"}]
    monkeypatch.setenv("DATABASE_URL", "postgresql://test")
    monkeypatch.setattr("api.cron.daily_prices.get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr("api.cron.daily_prices.price_universe", AsyncMock(return_value=["A"]))
    monkeypatch.setattr("api.cron.daily_prices.latest_completed_xnys_session", lambda _: datetime(2026, 11, 5).date())
    ticker = Mock()
    ticker.history.return_value = pd.DataFrame({"Close": [float("nan"), 100, 101]},
                                             index=pd.to_datetime(["2026-11-04", "2026-11-05", "2026-11-06"]))
    monkeypatch.setattr("api.cron.daily_prices.get_ticker", lambda _: ticker)
    upsert = AsyncMock()
    monkeypatch.setattr("api.cron.daily_prices.upsert_daily_close", upsert)
    monkeypatch.setattr("alpha_agent.backtest.consistency.materialize_outcomes", AsyncMock(return_value=0))
    result = await handler(limit=5)
    assert result["rows_processed"] == 1
    assert result["fresh_count"] == 1
    upsert.assert_awaited_once_with(pool, "A", "2026-11-05", 100.0)
