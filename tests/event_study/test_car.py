from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pandas as pd
import pytest

from alpha_agent.event_study.car_calculator import compute_car
from alpha_agent.storage.postgres import close_pool, get_pool


@pytest.fixture
async def pool(applied_db):
    p = await get_pool(applied_db)
    yield p
    await close_pool()


def _bars(start_price: float, drift_per_min: float, n: int):
    idx = pd.date_range("2026-05-15 14:30", periods=n, freq="1min", tz="UTC")
    closes = [start_price + i * drift_per_min for i in range(n)]
    return pd.DataFrame({"ts": idx, "close": closes})


@pytest.mark.asyncio
async def test_car_simple_positive(pool):
    """Ticker drifts +0.005/min for 60min = +0.5%, SPY drifts +0.002/min for 60min = +0.2%.
    CAR = (60 * 0.005 / 100) - (60 * 0.002 / 100) = 0.3% / 100 = 0.003."""
    ticker_df = _bars(100.0, 0.005, 61)
    spy_df    = _bars(400.0, 0.008, 61)  # 0.008/400 = 0.002% per min, 0.12% over 60min

    async def fake_get(pool, t, ev, w):
        return ticker_df if t == "AAPL" else spy_df

    with patch("alpha_agent.event_study.car_calculator.get_bars_for_event", new=fake_get):
        res = await compute_car(None, "AAPL",
                                datetime(2026, 5, 15, 14, 30, tzinfo=UTC), 60)
    assert res is not None
    # ticker: (100.30 - 100.0) / 100.0 = 0.003 = 0.3%
    assert abs(res.ticker_return - 0.003) < 1e-4
    # spy: (400.48 - 400.0) / 400.0 = 0.0012 = 0.12%
    assert abs(res.spy_return - 0.0012) < 1e-4
    assert abs(res.car_pct - (0.003 - 0.0012)) < 1e-4
    assert res.n_bars >= 60


@pytest.mark.asyncio
async def test_car_returns_none_when_ticker_bars_missing(pool):
    empty = pd.DataFrame(columns=["ts", "close"])
    spy   = _bars(400.0, 0.001, 61)

    async def fake_get(pool, t, ev, w):
        return empty if t == "AAPL" else spy

    with patch("alpha_agent.event_study.car_calculator.get_bars_for_event", new=fake_get):
        res = await compute_car(None, "AAPL",
                                datetime(2026, 5, 15, 14, 30, tzinfo=UTC), 60)
    assert res is None
