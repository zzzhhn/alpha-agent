"""Options sentiment from put/call volume ratio + IV percentile.

Academic anchors (added 2026-05-18):
- Primary modern reference: Cremers & Weinbaum (2010, JFQA 45(2))
  "Deviations from Put-Call Parity and Stock Return Predictability" —
  volatility spread (IV_call - IV_put for matched ATM strikes) is
  theoretically cleaner than raw PCR. Under put-call parity it should be
  zero; persistent deviation indicates directional information. Long-short
  on IV spread earns ~50bps/month alpha. Tractable from yfinance option_chain.
- Skew-based alternative: Xing, Zhang, Zhao (2010, JFQA 45(3)) "What Does
  the Individual Option Volatility Smirk Tell Us?" — OTM put skew predicts
  negative returns; needs wide option chain to compute reliably.
- Companion triangulation: Bali & Hovakimian (2009, Mgmt Sci 55(11))
  "Volatility Spreads and Expected Stock Returns" — replicates CW 2010 on
  different sample.
- Historical anchor: Pan & Poteshman (2006, RFS 19(3)) "The Information in
  Option Volume for Future Stock Prices" foundational PCR predictability.

Phase X TBD: replace placeholder IV-percentile term with Cremers-Weinbaum
volatility spread. New composite:
  z = 0.4 * (-pcr_z) + 0.6 * tanh(vs / 0.02)
where vs = mean(IV_call_ATM - IV_put_ATM) for nearest-expiry ATM strikes.
"""
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
