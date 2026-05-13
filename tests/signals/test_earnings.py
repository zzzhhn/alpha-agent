# tests/signals/test_earnings.py
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pandas as pd

from alpha_agent.signals.earnings import fetch_signal


def _ticker_mock(info=None, earnings_dates_df=None, calendar_df=None):
    m = MagicMock()
    m.info = info or {}
    m.earnings_dates = earnings_dates_df
    m.calendar = calendar_df
    return m


def test_recent_beat_yields_positive_z():
    info = {"epsActual": 1.20, "epsEstimate": 1.00}
    edates = pd.DataFrame(
        {"Reported EPS": [1.20], "EPS Estimate": [1.00]},
        index=pd.DatetimeIndex([datetime.now(UTC) - timedelta(days=5)]),
    )
    cal = pd.DataFrame(
        {"Earnings Date": [pd.Timestamp("2026-07-31", tz="UTC")],
         "EPS Estimate": [1.45], "Revenue Estimate": [120_000_000_000]}
    )
    with patch("alpha_agent.signals.earnings.get_ticker",
               return_value=_ticker_mock(info, edates, cal)):
        out = fetch_signal("AAPL", datetime.now(UTC))
    assert out["z"] > 0
    assert out["raw"]["surprise_pct"] > 0
    # New structured upcoming-earnings fields
    assert out["raw"]["next_date"] == "2026-07-31"
    assert out["raw"]["eps_estimate"] == 1.45
    assert out["raw"]["revenue_estimate"] == 120_000_000_000


def test_no_data_low_confidence():
    with patch("alpha_agent.signals.earnings.get_ticker",
               return_value=_ticker_mock()):
        out = fetch_signal("XYZ", datetime.now(UTC))
    assert out["confidence"] < 0.4


def test_no_upcoming_calendar_returns_null_fields():
    """If yf.Ticker.calendar is None but earnings_dates has a row,
    surprise_pct still populates while next_date/eps_estimate stay None."""
    info = {"epsActual": 1.20, "epsEstimate": 1.00}
    edates = pd.DataFrame(
        {"Reported EPS": [1.20], "EPS Estimate": [1.00]},
        index=pd.DatetimeIndex([datetime.now(UTC) - timedelta(days=5)]),
    )
    with patch("alpha_agent.signals.earnings.get_ticker",
               return_value=_ticker_mock(info, edates, None)):
        out = fetch_signal("AAPL", datetime.now(UTC))
    assert out["raw"]["surprise_pct"] > 0
    assert out["raw"]["next_date"] is None
    assert out["raw"]["eps_estimate"] is None
