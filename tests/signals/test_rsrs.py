"""Unit tests for the RSRS timing signal (alpha_agent/signals/rsrs.py)."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import numpy as np
import pandas as pd

from alpha_agent.signals import rsrs

_AS_OF = datetime(2026, 6, 18)


def test_rolling_slope_recovers_known_beta():
    # high = 5 + 2*low exactly -> trailing OLS slope must be 2.0.
    low = pd.Series(np.arange(1, 60, dtype=float))
    high = 5.0 + 2.0 * low
    s = rsrs._rolling_slope(high, low, rsrs._N_REG)
    assert abs(float(s.iloc[-1]) - 2.0) < 1e-9


def _df(n: int, noisy: bool) -> pd.DataFrame:
    low = np.linspace(100.0, 200.0, n)
    high = 1.0 + 2.0 * low
    if noisy:
        # vary the slope window-to-window so the z-score denominator is non-zero
        rng = np.random.default_rng(42)
        high = high + rng.normal(0.0, 0.8, n)
    return pd.DataFrame({"High": high, "Low": low})


def test_insufficient_history_zero_confidence():
    with patch.object(rsrs, "_download_ohlc", return_value=_df(rsrs._MIN_ROWS - 5, True)):
        s = rsrs.fetch_signal("AAA", _AS_OF)
    assert s["confidence"] == 0.0
    assert s["z"] == 0.0
    assert s["error"] is not None


def test_sufficient_history_returns_clipped_z():
    with patch.object(rsrs, "_download_ohlc", return_value=_df(rsrs._MIN_ROWS + 40, True)):
        s = rsrs.fetch_signal("AAA", _AS_OF)
    assert s["confidence"] == 0.7
    assert s["error"] is None
    assert -3.0 <= s["z"] <= 3.0
    assert s["raw"]["n_reg"] == rsrs._N_REG
    assert s["raw"]["m_window"] == rsrs._M_WINDOW
