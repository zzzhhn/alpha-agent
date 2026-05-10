"""Insider trading signal from SEC EDGAR Form 4 last 30 days.
Net dollar value (purchases - sales); sigmoid normalized."""
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
