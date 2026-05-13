# tests/signals/test_factor.py
from datetime import UTC, datetime
from unittest.mock import patch

from alpha_agent.signals.factor import fetch_signal


def test_factor_signal_happy_path():
    fake_scores = {"AAPL": 1.8, "MSFT": 0.5, "GOOG": -1.2}
    fake_info = {
        "trailingPE": 28.5, "forwardPE": 26.0, "trailingEps": 6.42,
        "marketCap": 3_200_000_000_000, "dividendYield": 0.0043,
        "profitMargins": 0.246, "debtToEquity": 145.3, "beta": 1.21,
    }
    with patch("alpha_agent.signals.factor._evaluate_for_universe",
               return_value=fake_scores), \
         patch("alpha_agent.signals.factor._fetch_info_for",
               return_value=fake_info):
        out = fetch_signal("AAPL", datetime.now(UTC))
    assert -3.0 <= out["z"] <= 3.0
    # raw is now a dict, not a float — UI block consumes raw["fundamentals"]
    assert isinstance(out["raw"], dict)
    assert out["raw"]["z"] == 1.8
    assert out["raw"]["fundamentals"]["pe_trailing"] == 28.5
    assert out["raw"]["fundamentals"]["market_cap"] == 3_200_000_000_000
    assert out["confidence"] > 0.5
    assert out["source"] == "factor_engine"


def test_factor_signal_unknown_ticker_returns_zero_confidence():
    fake_scores = {"MSFT": 0.5}
    with patch("alpha_agent.signals.factor._evaluate_for_universe",
               return_value=fake_scores):
        out = fetch_signal("UNKN", datetime.now(UTC))
    assert out["z"] == 0.0
    assert out["confidence"] == 0.0
    assert out["error"] is not None


def test_factor_signal_fundamentals_unavailable_keeps_z():
    """If yfinance info fetch fails, we still emit the z score with
    fundamentals=None — the rating logic doesn't depend on UI fields."""
    fake_scores = {"AAPL": 1.8}
    with patch("alpha_agent.signals.factor._evaluate_for_universe",
               return_value=fake_scores), \
         patch("alpha_agent.signals.factor._fetch_info_for",
               side_effect=KeyError("info missing")):
        out = fetch_signal("AAPL", datetime.now(UTC))
    assert out["z"] != 0.0  # z survives even though info fetch failed
    assert out["raw"]["fundamentals"] is None
