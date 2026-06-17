from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pandas as pd
import pytest

from alpha_agent.data.minute_price import (
    pull_and_store_minute_bars,
    get_bars_for_event,
)
from alpha_agent.storage.postgres import close_pool, get_pool


@pytest.fixture
async def pool(applied_db):
    p = await get_pool(applied_db)
    yield p
    await close_pool()


# Base timestamp a few days back so the seeded bars stay inside
# get_bars_for_event's 30-day coverage window regardless of the wall-clock date
# the suite runs on (a hardcoded date silently aged out of the window).
_BASE_TS = (datetime.now(UTC) - timedelta(days=3)).replace(
    hour=14, minute=30, second=0, microsecond=0
)


def _fake_df():
    """yfinance Ticker.history(period='7d', interval='1m') shape."""
    idx = pd.date_range(_BASE_TS, periods=60, freq="1min", tz="UTC")
    return pd.DataFrame({
        "Open": [100.0 + i * 0.01 for i in range(60)],
        "High": [100.5 + i * 0.01 for i in range(60)],
        "Low":  [ 99.5 + i * 0.01 for i in range(60)],
        "Close":[100.2 + i * 0.01 for i in range(60)],
        "Volume": [1000] * 60,
    }, index=idx)


@pytest.mark.asyncio
async def test_pull_upserts_rows(pool):
    with patch("alpha_agent.data.minute_price._yf_history", return_value=_fake_df()):
        n = await pull_and_store_minute_bars(pool, "AAPL")
    assert n == 60
    row = await pool.fetchval("SELECT count(*) FROM minute_bars WHERE ticker='AAPL'")
    assert row == 60


@pytest.mark.asyncio
async def test_get_bars_for_event_returns_window(pool):
    with patch("alpha_agent.data.minute_price._yf_history", return_value=_fake_df()):
        await pull_and_store_minute_bars(pool, "AAPL")
    event_ts = _BASE_TS + timedelta(minutes=5)
    bars = await get_bars_for_event(pool, "AAPL", event_ts, window_min=20)
    # 20 minutes from event_ts (5 min into the 60-min fixture), expect ~20 rows
    assert 18 <= len(bars) <= 22


@pytest.mark.asyncio
async def test_event_beyond_30d_returns_empty(pool):
    """Spec requirement: events older than 30d have no minute coverage."""
    event_ts = datetime.now(UTC) - timedelta(days=45)
    bars = await get_bars_for_event(pool, "AAPL", event_ts, window_min=60)
    assert bars.empty or len(bars) == 0
