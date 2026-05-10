"""Technical-indicator composite signal.

Sub-indicators (each z-scored cross-section, then equal-weighted):
  - RSI(14): mean-reversion / momentum gauge
  - MACD histogram: trend strength
  - ATR(14) / price: volatility-normalized risk
  - 50d MA distance: short-term trend
  - 200d MA distance: long-term trend
Spec §3.1 weight 0.20.
"""
from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd

from alpha_agent.signals.base import SignalScore, safe_fetch


def _download_ohlcv(ticker: str, as_of: datetime) -> pd.DataFrame:
    import yfinance as yf
    end = as_of.date().isoformat()
    start = (as_of.date() - pd.Timedelta(days=400)).isoformat()
    df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df


def _rsi(close: pd.Series, n: int = 14) -> float:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(n).mean()
    loss = (-delta.clip(upper=0)).rolling(n).mean()
    rs = gain / loss.replace(0, np.nan)
    return float(100 - 100 / (1 + rs.iloc[-1])) if pd.notna(rs.iloc[-1]) else 50.0


def _macd_hist(close: pd.Series) -> float:
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    return float((macd - signal).iloc[-1])


def _atr(df: pd.DataFrame, n: int = 14) -> float:
    high, low, close = df["High"], df["Low"], df["Close"]
    tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    return float(tr.rolling(n).mean().iloc[-1])


def _fetch(ticker: str, as_of: datetime) -> SignalScore:
    df = _download_ohlcv(ticker, as_of)
    if len(df) < 60:
        return SignalScore(
            ticker=ticker, z=0.0, raw=None, confidence=0.3,
            as_of=as_of, source="yfinance",
            error=f"insufficient history ({len(df)} rows)",
        )
    close = df["Close"]
    components = {
        "rsi": _rsi(close),
        "macd": _macd_hist(close),
        "atr": _atr(df) / float(close.iloc[-1]),
        "ma50_dist": float(close.iloc[-1] / close.rolling(50).mean().iloc[-1] - 1),
        "ma200_dist": float(close.iloc[-1] / close.rolling(200).mean().iloc[-1] - 1),
    }
    rsi_z = (components["rsi"] - 50) / 20
    macd_z = np.tanh(components["macd"] / max(close.std(), 1e-6))
    atr_z = -np.tanh(components["atr"] * 50)
    ma50_z = np.tanh(components["ma50_dist"] * 10)
    ma200_z = np.tanh(components["ma200_dist"] * 10)
    z = float(np.clip(np.mean([rsi_z, macd_z, atr_z, ma50_z, ma200_z]), -3.0, 3.0))
    return SignalScore(
        ticker=ticker, z=z, raw=components, confidence=0.85,
        as_of=as_of, source="yfinance", error=None,
    )


def fetch_signal(ticker: str, as_of: datetime) -> SignalScore:
    return safe_fetch(_fetch, ticker, as_of, source="yfinance")
