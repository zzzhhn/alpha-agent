"""RSRS (Resistance Support Relative Strength) timing signal.

Origin: 光大证券 (2017), designed for A-share index timing. For each day, run an
OLS regression of the trailing-N daily HIGHs on the trailing-N daily LOWs; the
slope beta is the raw RSRS. A steep slope means resistance is rising faster than
support (bullish); a flat/negative slope means support is giving way (bearish).
The raw slope is standardized to a z-score over a trailing M-day window so it is
comparable across regimes and (here) cross-sectionally across names.

Used here as a cross-sectional tilt (like `technicals`): the returned `z` is the
RSRS z-score itself, clipped to [-3, 3]. It is a deliberately WEAK-ALONE
diversifier, not a standalone timer.

Params validated on US equities (scripts/rsrs_validation.py, 2026-06-19):
N=18, M=126 give a positive cross-sectional IC (~0.043, IC_IR ~0.22, 61% of days
positive) at the ~20-day horizon. The A-share original M=600 does NOT transfer
(M=252 went IC-negative on US names), hence M=126 is the chosen window. Because
the edge is modest and decorrelated, it carries a small fusion weight.
"""
from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd

from alpha_agent.signals.base import SignalScore, safe_fetch

_N_REG = 18      # high~low regression window (the RSRS slope)
_M_WINDOW = 126  # z-score standardization window (US sweet spot; NOT the A-share 600)
_MIN_ROWS = _N_REG + _M_WINDOW  # need at least this much history for a z-score


def _download_ohlc(ticker: str, as_of: datetime) -> pd.DataFrame:
    import yfinance as yf
    end = as_of.date().isoformat()
    # ~1.5 calendar years covers N + M (~144 trading days) with comfortable slack.
    start = (as_of.date() - pd.Timedelta(days=420)).isoformat()
    df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df


def _rolling_slope(high: pd.Series, low: pd.Series, n: int) -> pd.Series:
    """Trailing-n OLS slope of high on low: beta = cov(low, high) / var(low)."""
    cov = low.rolling(n).cov(high)
    var = low.rolling(n).var()
    return cov / var.replace(0.0, np.nan)


def _fetch(ticker: str, as_of: datetime) -> SignalScore:
    df = _download_ohlc(ticker, as_of)
    if len(df) < _MIN_ROWS or not {"High", "Low"}.issubset(df.columns):
        return SignalScore(
            ticker=ticker, z=0.0, raw=None, confidence=0.0,
            as_of=as_of, source="yfinance",
            error=f"insufficient history ({len(df)} rows, need {_MIN_ROWS})",
        )
    beta = _rolling_slope(df["High"], df["Low"], _N_REG)
    mu = beta.rolling(_M_WINDOW).mean().iloc[-1]
    sd = beta.rolling(_M_WINDOW).std().iloc[-1]
    slope = float(beta.iloc[-1]) if pd.notna(beta.iloc[-1]) else None
    if slope is None or pd.isna(mu) or pd.isna(sd) or sd == 0:
        return SignalScore(
            ticker=ticker, z=0.0, raw={"slope": slope}, confidence=0.0,
            as_of=as_of, source="yfinance",
            error="degenerate RSRS (flat slope window or zero variance)",
        )
    z = float(np.clip((slope - float(mu)) / float(sd), -3.0, 3.0))
    return SignalScore(
        ticker=ticker, z=z,
        raw={"slope": slope, "zscore": z, "n_reg": _N_REG, "m_window": _M_WINDOW},
        # Modest confidence: a real but weak, decorrelated timing tilt (see module
        # docstring); it is meant to be fused, never to drive a call on its own.
        confidence=0.7,
        as_of=as_of, source="yfinance", error=None,
    )


def fetch_signal(ticker: str, as_of: datetime) -> SignalScore:
    return safe_fetch(_fetch, ticker, as_of, source="yfinance")
