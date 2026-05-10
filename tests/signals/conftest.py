"""Shared signal-test fixtures: frozen yfinance / EDGAR / FRED responses."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

FIXTURE_ROOT = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def yf_ohlcv_aapl_2024() -> pd.DataFrame:
    path = FIXTURE_ROOT / "yfinance" / "AAPL_ohlcv_2024-01-01_2024-12-31.json"
    raw = json.loads(path.read_text())
    return pd.DataFrame(raw).rename(columns=str.title)
