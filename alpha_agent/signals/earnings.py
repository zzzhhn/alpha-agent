# alpha_agent/signals/earnings.py
"""Earnings catalyst signal. Two components:
- Proximity: |days_until_or_since_earnings|; sigmoid -> [0, 1]
- Surprise: (actual - estimate) / |estimate|; +-50% saturates."""
from __future__ import annotations
from datetime import datetime
import numpy as np
from alpha_agent.signals.base import SignalScore, safe_fetch


def _fetch_info(ticker: str) -> dict:
    import yfinance as yf
    t = yf.Ticker(ticker)
    info = t.info or {}
    earnings_dates = getattr(t, "earnings_dates", None)
    if earnings_dates is not None and not earnings_dates.empty:
        info["epsActual"] = earnings_dates["Reported EPS"].iloc[0]
        info["epsEstimate"] = earnings_dates["EPS Estimate"].iloc[0]
        info["earningsDate"] = [earnings_dates.index[0]]
    return info


def _fetch(ticker: str, as_of: datetime) -> SignalScore:
    info = _fetch_info(ticker)
    actual = info.get("epsActual")
    est = info.get("epsEstimate")
    earn_dates = info.get("earningsDate") or []
    if not earn_dates or actual is None or est is None or est == 0:
        return SignalScore(ticker=ticker, z=0.0, raw=None, confidence=0.3,
                           as_of=as_of, source="yfinance", error="missing earnings")
    surprise = (actual - est) / abs(est)
    surprise_z = float(np.clip(surprise / 0.20, -2.0, 2.0))
    days = abs((earn_dates[0].replace(tzinfo=as_of.tzinfo) - as_of).days)
    proximity_w = float(np.exp(-days / 14))
    z = float(np.clip(surprise_z * proximity_w, -3.0, 3.0))
    return SignalScore(
        ticker=ticker, z=z,
        raw={"surprise_pct": surprise * 100, "days_to_earnings": days},
        confidence=0.75, as_of=as_of, source="yfinance", error=None,
    )


def fetch_signal(ticker: str, as_of: datetime) -> SignalScore:
    return safe_fetch(_fetch, ticker, as_of, source="yfinance")
