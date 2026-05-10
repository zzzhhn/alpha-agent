from datetime import datetime, UTC
from unittest.mock import patch

from alpha_agent.signals.technicals import fetch_signal


def test_technicals_z_in_valid_range(yf_ohlcv_aapl_2024):
    with patch("alpha_agent.signals.technicals._download_ohlcv",
               return_value=yf_ohlcv_aapl_2024):
        out = fetch_signal("AAPL", datetime(2024, 12, 15, tzinfo=UTC))
    assert -3.0 <= out["z"] <= 3.0
    assert isinstance(out["raw"], dict)
    assert {"rsi", "macd", "atr", "ma50_dist", "ma200_dist"} <= out["raw"].keys()
    assert out["confidence"] > 0.7


def test_technicals_short_history_returns_low_confidence(yf_ohlcv_aapl_2024):
    df = yf_ohlcv_aapl_2024.tail(30)  # only 30 rows
    with patch("alpha_agent.signals.technicals._download_ohlcv", return_value=df):
        out = fetch_signal("AAPL", datetime(2024, 12, 15, tzinfo=UTC))
    assert out["confidence"] < 0.5
