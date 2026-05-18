"""Insider trading signal from SEC EDGAR Form 4 last 30 days.
Net dollar value (purchases - sales); sigmoid normalized.

Academic anchors (added 2026-05-18):
- Primary modern reference: Cohen, Malloy, Pomorski (2012, JoF 67(3))
  "Decoding Inside Information" — distinguishes *routine* (predictable,
  scheduled, no info) from *opportunistic* (irregular timing, info-loaded)
  insider trades. Opportunistic buys earn ~10%/yr alpha; routine trades
  earn ~0. Our current aggregation mixes both and dilutes signal.
- Attention refinement: Alldredge & Cicero (2015, JFE 115(1)) "Attentive
  Insider Trading" — insiders monitoring outside info generate larger
  profits; refinable with premium SEC EDGAR access logs.
- Firm-level trait: Ali & Hirshleifer (2017, JFE 126(3)) "Opportunism as
  a Firm and Managerial Trait" — firm-level opportunism score complements
  per-trade classification.
- Historical anchors: Seyhun (1986, JFE; 1998 book "Investment
  Intelligence from Insider Trading") foundational US insider alpha;
  Lakonishok & Lee (2001, RFS 14(1)) systematic insider sort returns.

Phase X TBD: add routine-vs-opportunistic classifier — simplest version
flags an insider as "routine" if their trade-month-of-year SD < threshold
(trades cluster in same calendar months). Score:
  z = tanh(opportunistic_net / 500k) + 0.3 * tanh(routine_net / 1M)"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx
import numpy as np

from alpha_agent.signals.base import SignalScore, safe_fetch

_EDGAR_HEADERS = {"User-Agent": "Alpha Agent v4 contact@example.com"}


def _fetch_form4_30d(ticker: str, as_of: datetime) -> list[dict[str, Any]]:
    """Returns list of {date, code (P/S), shares, value}."""
    url = f"https://data.sec.gov/submissions/CIK{ticker}.json"
    resp = httpx.get(url, headers=_EDGAR_HEADERS, timeout=10.0)
    resp.raise_for_status()
    # Real implementation: parse Form 4 filings; placeholder here.
    return []  # replaced by tests via patch


def _fetch(ticker: str, as_of: datetime) -> SignalScore:
    fills = _fetch_form4_30d(ticker, as_of)
    if not fills:
        return SignalScore(
            ticker=ticker, z=0.0,
            raw={"net_value": 0, "n_fillings": 0},
            confidence=0.4, as_of=as_of, source="edgar",
            error="no filings in 30d",
        )
    net = sum(f["value"] if f["code"] == "P" else -f["value"] for f in fills)
    z = float(np.tanh(net / 1_000_000))
    return SignalScore(
        ticker=ticker, z=z,
        raw={"net_value": net, "n_fillings": len(fills)},
        confidence=0.70, as_of=as_of, source="edgar", error=None,
    )


def fetch_signal(ticker: str, as_of: datetime) -> SignalScore:
    return safe_fetch(_fetch, ticker, as_of, source="edgar")
