"""Analyst consensus signal. yfinance .info exposes recommendationKey
('strong_buy'|'buy'|'hold'|'underperform'|'sell') + targetMeanPrice.
We map the key to [-2, +2] and target upside to [-1, +1], average."""
from __future__ import annotations
from datetime import datetime
from alpha_agent.signals.base import SignalScore, safe_fetch

_REC_MAP = {
    "strong_buy": 2.0, "buy": 1.0, "hold": 0.0,
    "underperform": -1.0, "sell": -2.0, "strong_sell": -2.0,
}


def _fetch_info(ticker: str) -> dict:
    import yfinance as yf
    return yf.Ticker(ticker).info or {}


def _fetch(ticker: str, as_of: datetime) -> SignalScore:
    info = _fetch_info(ticker)
    rec = (info.get("recommendationKey") or "").lower()
    cur = info.get("currentPrice")
    tgt = info.get("targetMeanPrice")
    if rec not in _REC_MAP:
        return SignalScore(ticker=ticker, z=0.0, raw=None, confidence=0.2,
                           as_of=as_of, source="yfinance",
                           error="missing recommendationKey")
    rec_z = _REC_MAP[rec] / 2.0  # -> [-1, +1]
    target_upside_z = 0.0
    if cur and tgt:
        upside = (tgt - cur) / cur
        target_upside_z = max(min(upside / 0.20, 1.0), -1.0)  # ±20% saturates
    z = max(min((rec_z + target_upside_z) / 2 * 2, 3.0), -3.0)
    return SignalScore(
        ticker=ticker, z=z,
        raw={"recommendation": rec, "current": cur, "target": tgt},
        confidence=0.80, as_of=as_of, source="yfinance", error=None,
    )


def fetch_signal(ticker: str, as_of: datetime) -> SignalScore:
    return safe_fetch(_fetch, ticker, as_of, source="yfinance")
