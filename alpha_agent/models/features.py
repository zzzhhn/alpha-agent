"""Feature engineering for ML models — transforms raw OHLCV into model inputs."""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def compute_features(ohlcv: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """Compute technical features for a single ticker.

    Parameters
    ----------
    ohlcv : pd.DataFrame
        MultiIndex (date, stock_code) with columns: open, high, low, close, volume.
    ticker : str
        Ticker to filter from the MultiIndex.

    Returns
    -------
    pd.DataFrame
        DatetimeIndex with feature columns (NaN rows from lookback are dropped).
    """
    df = ohlcv.xs(ticker, level="stock_code").copy()
    close = df["close"]

    features = pd.DataFrame(index=df.index)
    features["log_return"] = np.log(close / close.shift(1))
    features["volatility_20d"] = features["log_return"].rolling(20).std()
    features["rsi_14"] = _rsi(close, 14)
    features["macd"] = _macd(close)
    features["bollinger_pctb"] = _bollinger_pctb(close, 20)

    return features.dropna()


def compute_forward_returns(ohlcv: pd.DataFrame, ticker: str, horizon: int = 5) -> pd.Series:
    """Compute forward returns for direction labeling.

    Returns a Series of +1 (up) / 0 (down) aligned to the feature index.
    """
    df = ohlcv.xs(ticker, level="stock_code")
    close = df["close"]
    fwd = close.shift(-horizon) / close - 1.0
    return (fwd > 0).astype(int).dropna()


# --------------------------------------------------------------------------- #
# Technical indicators (pure functions, no mutation)
# --------------------------------------------------------------------------- #


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index."""
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))


def _macd(close: pd.Series, fast: int = 12, slow: int = 26) -> pd.Series:
    """MACD line (fast EMA - slow EMA), normalized by price."""
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    return (ema_fast - ema_slow) / close


def _bollinger_pctb(close: pd.Series, period: int = 20) -> pd.Series:
    """Bollinger %B — position within the Bollinger Bands (0-1 range)."""
    sma = close.rolling(period).mean()
    std = close.rolling(period).std()
    upper = sma + 2 * std
    lower = sma - 2 * std
    width = upper - lower
    return (close - lower) / width.replace(0, np.nan)
