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


def test_sue_uses_historical_std_when_4q_available():
    """Regression for Foster-Olsen-Shevlin SUE: with 4+ quarters of low-vol
    surprise history (sigma ≈ 0.05), a +20% surprise should now score much
    higher than under the legacy 0.20 cap. Without history, fallback to
    0.20 preserves prior behavior."""
    info = {"epsActual": 1.20, "epsEstimate": 1.00}
    # 5 prior quarters with tiny ±2% surprises → sigma ≈ 0.02 (floored to 0.05)
    quarterly_dates = pd.DatetimeIndex(
        [datetime.now(UTC) - timedelta(days=90 * i) for i in range(5)]
    )
    edates = pd.DataFrame(
        {
            "Reported EPS": [1.20, 1.02, 0.98, 1.02, 0.99],
            "EPS Estimate": [1.00, 1.00, 1.00, 1.00, 1.00],
        },
        index=quarterly_dates,
    )
    with patch("alpha_agent.signals.earnings.get_ticker",
               return_value=_ticker_mock(info, edates, None)):
        out = fetch_signal("AAPL", datetime.now(UTC))
    # +20% surprise with sigma_floor=0.05 → SUE = 4.0 (clipped to 3.0)
    # vs legacy 0.20 cap → SUE = 1.0. New score must be meaningfully higher.
    assert out["z"] > 1.5, (
        f"SUE-standardized z should be >1.5 with low historical sigma, got {out['z']}"
    )


def test_sue_falls_back_to_legacy_cap_when_sparse_history():
    """One quarter of history → not enough for SUE → uses 0.20 fallback,
    preserving legacy behavior (z ≈ 0.7 = 1.0 * exp(-5/14))."""
    info = {"epsActual": 1.20, "epsEstimate": 1.00}
    edates = pd.DataFrame(
        {"Reported EPS": [1.20], "EPS Estimate": [1.00]},
        index=pd.DatetimeIndex([datetime.now(UTC) - timedelta(days=5)]),
    )
    with patch("alpha_agent.signals.earnings.get_ticker",
               return_value=_ticker_mock(info, edates, None)):
        out = fetch_signal("AAPL", datetime.now(UTC))
    # surprise/0.20 = 1.0, proximity = exp(-5/14) ≈ 0.70, z ≈ 0.70
    assert 0.5 < out["z"] < 0.9, f"Legacy cap should give z≈0.70, got {out['z']}"
