"""Pre-market gap normalized by 14-day ATR. Captures overnight news
priced into the open. Only meaningful pre-9:30 ET; safe_fetch returns
zero-confidence outside that window in real impl.

Spec §3.1 weight 0.05.

Academic anchors (added 2026-05-18):
- Primary modern reference: Berkman, Koch, Tuttle, Zhang (2012, JFQA 47(4))
  "Paying Attention: Overnight Returns and the Hidden Cost of Buying at the
  Open" — systematic overnight-vs-intraday return decomposition incl. the
  cost of trading the open against retail attention-driven order imbalance.
- Decomposition validation: Lou, Polk, Skouras (2019, JFE 134(1)) "A Tug of
  War: Overnight versus Intraday Expected Returns" — long-term US equity
  premium is entirely overnight; validates premium attribution.
- Cross-section: Bogousslavsky (2021, JFE 141(1)) "The Cross-Section of
  Intraday and Overnight Returns" — momentum is largely overnight, reversal
  largely intraday. Highly relevant when combining premarket with factor.

Phase X TBD: (a) asymmetric clip (overnight gap-ups mean-revert more than
gap-downs per disposition effect): `clip(gap/atr, -3, 2)`. (b) Add a
gap-and-go vs gap-and-fade flag based on first 15-min volume — high-volume
gaps follow through, low-volume gaps fade. Threshold ~150% of avg-first-15-min
volume.
"""
from __future__ import annotations

from datetime import datetime

import numpy as np

from alpha_agent.signals.base import SignalScore, safe_fetch


def _fetch_premarket(ticker: str, as_of: datetime) -> dict:
    import yfinance as yf
    t = yf.Ticker(ticker)
    info = t.info or {}
    # atr14 placeholder: real impl downloads 14d OHLCV and computes true ATR
    return {
        "preMarketPrice": info.get("preMarketPrice"),
        "regularMarketPreviousClose": info.get("regularMarketPreviousClose"),
        "atr14": info.get("atr14"),  # populated by refresh_fixtures; None in live yf
    }


def _fetch(ticker: str, as_of: datetime) -> SignalScore:
    d = _fetch_premarket(ticker, as_of)
    pm = d.get("preMarketPrice")
    prev = d.get("regularMarketPreviousClose")
    atr = d.get("atr14")
    if not all([pm, prev, atr]) or atr == 0:
        return SignalScore(
            ticker=ticker, z=0.0, raw=None, confidence=0.3,
            as_of=as_of, source="yfinance", error="no pre-market data",
        )
    gap = pm - prev
    z = float(np.clip(gap / atr, -3.0, 3.0))
    return SignalScore(
        ticker=ticker, z=z,
        raw={"gap": gap, "gap_sigma": z},
        confidence=0.75, as_of=as_of, source="yfinance", error=None,
    )


def fetch_signal(ticker: str, as_of: datetime) -> SignalScore:
    return safe_fetch(_fetch, ticker, as_of, source="yfinance")
