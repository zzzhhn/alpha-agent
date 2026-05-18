from datetime import datetime, UTC
from unittest.mock import patch

from alpha_agent.signals.technicals import fetch_signal


def test_technicals_z_in_valid_range(yf_ohlcv_aapl_2024):
    with patch("alpha_agent.signals.technicals._download_ohlcv",
               return_value=yf_ohlcv_aapl_2024):
        out = fetch_signal("AAPL", datetime(2024, 12, 15, tzinfo=UTC))
    assert -3.0 <= out["z"] <= 3.0
    assert isinstance(out["raw"], dict)
    expected_keys = {
        "rsi", "macd", "atr", "atr_dollar", "current_price",
        "ma50_dist", "ma200_dist",
    }
    assert expected_keys <= out["raw"].keys()
    assert out["confidence"] > 0.7


def test_technicals_emits_atr_dollar_and_current_price(yf_ohlcv_aapl_2024):
    """Regression for 2026-05-18 ATR-unit bug: ActionBox needs ATR-dollar
    + current_price to render entry/stop/target without unit mismatch."""
    with patch("alpha_agent.signals.technicals._download_ohlcv",
               return_value=yf_ohlcv_aapl_2024):
        out = fetch_signal("AAPL", datetime(2024, 12, 15, tzinfo=UTC))
    raw = out["raw"]
    assert raw["atr_dollar"] > 0, "atr_dollar should be positive dollar value"
    assert raw["current_price"] > 0, "current_price should be positive"
    # atr ratio = atr_dollar / current_price by construction
    assert abs(raw["atr"] - raw["atr_dollar"] / raw["current_price"]) < 1e-9


def test_technicals_short_history_returns_low_confidence(yf_ohlcv_aapl_2024):
    df = yf_ohlcv_aapl_2024.tail(30)  # only 30 rows
    with patch("alpha_agent.signals.technicals._download_ohlcv", return_value=df):
        out = fetch_signal("AAPL", datetime(2024, 12, 15, tzinfo=UTC))
    assert out["confidence"] < 0.5
