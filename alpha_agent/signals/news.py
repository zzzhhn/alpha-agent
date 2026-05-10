"""News-flow signal via agent-reach. Each item carries a precomputed
sentiment in [-1, +1]; we average + count-bonus.

_search_recent is a placeholder; real agent-reach integration is deferred to M2/M3.
Spec §3.1 weight 0.10.
"""
from __future__ import annotations

from datetime import datetime

import numpy as np

from alpha_agent.signals.base import SignalScore, safe_fetch


def _search_recent(ticker: str, as_of: datetime) -> list[dict]:
    # Real impl: agent-reach plugin call. Returns list of items with `sentiment`.
    return []


def _fetch(ticker: str, as_of: datetime) -> SignalScore:
    items = _search_recent(ticker, as_of)
    if not items:
        return SignalScore(
            ticker=ticker, z=0.0, raw={"n": 0, "mean_sent": 0.0},
            confidence=0.3, as_of=as_of, source="agent-reach",
            error="no news in 24h",
        )
    sents = [it.get("sentiment", 0.0) for it in items]
    mean = float(np.mean(sents))
    count_bonus = float(np.tanh(len(items) / 10))  # more items → more confidence in direction
    z = float(np.clip(mean * 2 * count_bonus, -3.0, 3.0))
    return SignalScore(
        ticker=ticker, z=z,
        raw={"n": len(items), "mean_sent": mean, "headlines": [it["title"] for it in items[:5]]},
        confidence=0.65, as_of=as_of, source="agent-reach", error=None,
    )


def fetch_signal(ticker: str, as_of: datetime) -> SignalScore:
    return safe_fetch(_fetch, ticker, as_of, source="agent-reach")
