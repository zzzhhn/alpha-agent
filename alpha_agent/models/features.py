"""Feature engineering for ML models — transforms raw OHLCV into model inputs.

Supports two output modes:
  - compute_features()  → flat DataFrame (backward compat for ML training)
  - compute_features_rich() → list of FeatureRecord dicts with z_score/percentile
"""

from __future__ import annotations

import logging
from typing import TypedDict

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Type definitions
# --------------------------------------------------------------------------- #


class FeatureRecord(TypedDict):
    """Single feature entry matching the v2.0 data contract."""

    name: str
    value: float
    z_score: float
    percentile: float


class FeatureState(TypedDict):
    """Per-ticker feature state response (blueprint p9 data contract)."""

    ticker: str
    timestamp: str
    features: list[FeatureRecord]


class FeatureStats(TypedDict):
    """Feature statistics row for the stats table."""

    name: str
    value: float
    mean: float
    std: float
    min: float
    max: float


# --------------------------------------------------------------------------- #
# Core feature names — ordered for consistency
# --------------------------------------------------------------------------- #

FEATURE_NAMES: tuple[str, ...] = (
    "log_return",
    "volatility_20d",
    "rsi_14",
    "macd",
    "bollinger_pctb",
    "momentum_10d",
    "momentum_20d",
    "momentum_60d",
    "mean_reversion_score",
    "volume_anomaly",
)


# --------------------------------------------------------------------------- #
# Public API — backward compatible
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
    volume = df["volume"] if "volume" in df.columns else pd.Series(dtype=float)

    features = pd.DataFrame(index=df.index)

    # --- Original 5 features (backward compat) ---
    features["log_return"] = np.log(close / close.shift(1))
    features["volatility_20d"] = features["log_return"].rolling(20).std()
    features["rsi_14"] = _rsi(close, 14)
    features["macd"] = _macd(close)
    features["bollinger_pctb"] = _bollinger_pctb(close, 20)

    # --- New features (blueprint p7-9) ---
    features["momentum_10d"] = _momentum(close, 10)
    features["momentum_20d"] = _momentum(close, 20)
    features["momentum_60d"] = _momentum(close, 60)
    features["mean_reversion_score"] = _mean_reversion_score(close, 20)
    features["volume_anomaly"] = _volume_anomaly(volume, 20)

    return features.dropna()


def compute_features_rich(
    ohlcv: pd.DataFrame,
    ticker: str,
) -> FeatureState:
    """Compute features with z-score and percentile for each.

    Returns the v2.0 data contract format (blueprint p9).
    """
    features_df = compute_features(ohlcv, ticker)
    if features_df.empty:
        return FeatureState(ticker=ticker, timestamp="", features=[])

    latest_row = features_df.iloc[-1]
    timestamp = str(features_df.index[-1])

    records: list[FeatureRecord] = []
    for col in FEATURE_NAMES:
        if col not in features_df.columns:
            continue
        series = features_df[col].dropna()
        value = float(latest_row[col])
        z = _z_score(value, series)
        pct = _percentile(value, series)
        records.append(FeatureRecord(
            name=col,
            value=round(value, 6),
            z_score=round(z, 4),
            percentile=round(pct, 4),
        ))

    return FeatureState(
        ticker=ticker,
        timestamp=timestamp,
        features=records,
    )


def compute_feature_stats(ohlcv: pd.DataFrame, ticker: str) -> list[FeatureStats]:
    """Compute summary statistics for all features (blueprint p9 stats table).

    Returns list of {name, value, mean, std, min, max} dicts.
    """
    features_df = compute_features(ohlcv, ticker)
    if features_df.empty:
        return []

    result: list[FeatureStats] = []
    latest_row = features_df.iloc[-1]

    for col in FEATURE_NAMES:
        if col not in features_df.columns:
            continue
        series = features_df[col].dropna()
        result.append(FeatureStats(
            name=col,
            value=round(float(latest_row[col]), 6),
            mean=round(float(series.mean()), 6),
            std=round(float(series.std()), 6),
            min=round(float(series.min()), 6),
            max=round(float(series.max()), 6),
        ))

    return result


def compute_forward_returns(ohlcv: pd.DataFrame, ticker: str, horizon: int = 5) -> pd.Series:
    """Compute forward returns for direction labeling.

    Returns a Series of +1 (up) / 0 (down) aligned to the feature index.
    """
    df = ohlcv.xs(ticker, level="stock_code")
    close = df["close"]
    fwd = close.shift(-horizon) / close - 1.0
    return (fwd > 0).astype(int).dropna()


# --------------------------------------------------------------------------- #
# Statistical helpers
# --------------------------------------------------------------------------- #


def _z_score(value: float, series: pd.Series) -> float:
    """Z-score of value relative to the historical series."""
    if len(series) < 2:
        return 0.0
    std = float(series.std())
    if std == 0 or np.isnan(std):
        return 0.0
    return (value - float(series.mean())) / std


def _percentile(value: float, series: pd.Series) -> float:
    """Percentile rank of value within the series (0-1)."""
    if len(series) < 2:
        return 0.5
    return float(scipy_stats.percentileofscore(series, value, kind="rank") / 100.0)


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


def _momentum(close: pd.Series, period: int) -> pd.Series:
    """Price momentum: (close / close_n_ago) - 1."""
    return close / close.shift(period) - 1.0


def _mean_reversion_score(close: pd.Series, period: int = 20) -> pd.Series:
    """Mean reversion score: negative z-score of close vs rolling mean.

    High positive = price far below mean (potential long reversion).
    High negative = price far above mean (potential short reversion).
    """
    sma = close.rolling(period).mean()
    std = close.rolling(period).std()
    z = (close - sma) / std.replace(0, np.nan)
    # Invert: negative z (below mean) → positive reversion score
    return -z


def _volume_anomaly(volume: pd.Series, period: int = 20) -> pd.Series:
    """Volume anomaly: z-score of current volume vs rolling average.

    Positive = unusually high volume.
    """
    if volume.empty:
        return pd.Series(dtype=float)
    vol_mean = volume.rolling(period).mean()
    vol_std = volume.rolling(period).std()
    return (volume - vol_mean) / vol_std.replace(0, np.nan)
