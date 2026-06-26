from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pandas as pd
import pytest

from alpha_agent.data.minute_price import (
    MINUTE_BARS_RETENTION_DAYS,
    prune_minute_bars,
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


class _CapturePool:
    """Stub pool that records the DELETE issued by prune_minute_bars."""

    def __init__(self) -> None:
        self.query = None
        self.args = None

    async def execute(self, query, *args):
        self.query = query
        self.args = args
        return "DELETE 42"


def test_minute_bars_retention_is_two_days():
    """7-day retention (~1.4M rows, ~324MB) crowded out every other table on
    the 512MB Neon free tier and caused DiskFullError cascades (2026-06-26).
    2 days is all the intraday signals consume."""
    assert MINUTE_BARS_RETENTION_DAYS == 2


@pytest.mark.asyncio
async def test_prune_minute_bars_deletes_older_than_retention():
    pool = _CapturePool()
    status = await prune_minute_bars(pool)
    assert "minute_bars" in pool.query
    assert "DELETE" in pool.query.upper()
    # Parameterized interval so the window can't drift from the constant.
    assert pool.args == (MINUTE_BARS_RETENTION_DAYS,)
    assert status == "DELETE 42"
