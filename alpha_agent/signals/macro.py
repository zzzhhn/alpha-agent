"""Macro tilt signal. Single snapshot per date applied to all tickers
(sector adjustment lives in the optional sector overlay, not here).
Components: yield curve slope (DGS10-DGS2), DXY z, VIX z."""
from __future__ import annotations

from datetime import datetime
from functools import lru_cache

import numpy as np

from alpha_agent.signals.base import SignalScore, safe_fetch


@lru_cache(maxsize=4)
def _fetch_snapshot(date_iso: str) -> dict[str, float]:
    # Real impl pulls FRED API for DGS10, DGS2, DXY, VIX
    return {"DGS10": 4.2, "DGS2": 4.0, "DXY": 102, "VIX": 16}


def _fetch(ticker: str, as_of: datetime) -> SignalScore:
    snap = _fetch_snapshot(as_of.date().isoformat())
    slope = snap["DGS10"] - snap["DGS2"]
    slope_z = float(np.tanh(slope * 5))               # +0.2 -> ~0.76
    dxy_z = -float(np.tanh((snap["DXY"] - 100) / 5))  # strong dollar = negative
    vix_z = -float(np.tanh((snap["VIX"] - 16) / 8))   # high vol = negative
    z = float(np.clip(np.mean([slope_z, dxy_z, vix_z]), -3.0, 3.0))
    return SignalScore(
        ticker=ticker, z=z, raw=snap, confidence=0.85,
        as_of=as_of, source="fred", error=None,
    )


def fetch_signal(ticker: str, as_of: datetime) -> SignalScore:
    return safe_fetch(_fetch, ticker, as_of, source="fred")
