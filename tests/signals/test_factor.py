from datetime import datetime, UTC
from unittest.mock import patch

import numpy as np

from alpha_agent.signals.factor import fetch_signal


def test_factor_signal_happy_path():
    fake_scores = {"AAPL": 1.8, "MSFT": 0.5, "GOOG": -1.2}
    with patch("alpha_agent.signals.factor._evaluate_for_universe", return_value=fake_scores):
        out = fetch_signal("AAPL", datetime.now(UTC))
    assert -3.0 <= out["z"] <= 3.0
    assert out["raw"] == 1.8
    assert out["confidence"] > 0.5
    assert out["source"] == "factor_engine"


def test_factor_signal_unknown_ticker_returns_zero_confidence():
    fake_scores = {"MSFT": 0.5}
    with patch("alpha_agent.signals.factor._evaluate_for_universe", return_value=fake_scores):
        out = fetch_signal("UNKN", datetime.now(UTC))
    assert out["z"] == 0.0
    assert out["confidence"] == 0.0
    assert out["error"] is not None
