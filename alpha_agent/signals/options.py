"""Options sentiment from put/call volume ratio + IV percentile."""
from __future__ import annotations

from datetime import datetime

import numpy as np

from alpha_agent.signals.base import SignalScore, safe_fetch


def _fetch_chain(ticker: str, as_of: datetime) -> dict:
    import yfinance as yf
    t = yf.Ticker(ticker)
    expiries = t.options
    if not expiries:
        return {}
    chain = t.option_chain(expiries[0])
    return {
        "calls_volume": int(chain.calls["volume"].fillna(0).sum()),
        "puts_volume": int(chain.puts["volume"].fillna(0).sum()),
        "iv_percentile": 50.0,  # naive placeholder; full impl needs hist IV
    }


def _fetch(ticker: str, as_of: datetime) -> SignalScore:
    c = _fetch_chain(ticker, as_of)
    if not c or c.get("calls_volume", 0) + c.get("puts_volume", 0) == 0:
        return SignalScore(
            ticker=ticker, z=0.0, raw=None, confidence=0.3,
            as_of=as_of, source="yfinance", error="no options volume",
        )
    pcr = c["puts_volume"] / max(c["calls_volume"], 1)
    pcr_z = -float(np.tanh((pcr - 1.0) * 1.5))  # >1 (puts heavy) = negative
    iv_z = -float(np.tanh((c["iv_percentile"] - 50) / 30))
    z = float(np.clip((pcr_z + iv_z) / 2 * 2, -3.0, 3.0))
    return SignalScore(
        ticker=ticker, z=z, raw=c, confidence=0.70,
        as_of=as_of, source="yfinance", error=None,
    )


def fetch_signal(ticker: str, as_of: datetime) -> SignalScore:
    return safe_fetch(_fetch, ticker, as_of, source="yfinance")
