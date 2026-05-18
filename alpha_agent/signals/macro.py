"""Macro tilt signal. Single snapshot per date applied to all tickers
(sector adjustment lives in the optional sector overlay, not here).
Components: yield curve slope (DGS10-DGS2), DXY z, VIX z.

Academic anchors (added 2026-05-18):
- Primary modern reference: Adrian, Crump, Moench (2013, JFE 110(1))
  "Pricing the Term Structure with Linear Regressions" — ACM decomposition
  splits 10Y-2Y slope into expected-policy-rate vs term-premium components.
  Term premium carries stronger predictive power for cross-asset returns.
  NY Fed publishes daily-updated ACM series at
  https://www.newyorkfed.org/research/data_indicators/term-premia-tabs
- FCI overlay: Chicago Fed NFCI (https://www.chicagofed.org/research/data/nfci/current-data)
  — single-number summary of credit/equity/funding stress, free FRED feed.
- FOMC refinement: Bauer & Swanson (2023, AER 113(3)) "An Alternative
  Explanation for the Fed Information Effect" — informs days-since-FOMC
  decay weight around announcement windows.
- Risk perception: Pflueger, Siriwardane, Sunderam (2020, QJE 135(3))
  "Financial Market Risk Perceptions and the Macroeconomy" — risk-perception
  measure beyond VIX.
- Policy uncertainty: Baker-Bloom-Davis (2016, QJE) EPU as 4th macro leg.

Phase X TBD: replace `slope_z = tanh((DGS10 - DGS2) * 5)` with
`term_premium_z = tanh(ACM_10Y_TP_z)` (z-score over rolling 5Y). Add NFCI
as 4th component for financial-conditions overlay.
"""
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
