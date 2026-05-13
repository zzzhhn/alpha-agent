"""News-flow signal via yfinance Ticker.news (free, no API key).

Each headline gets a keyword-rule sentiment in {pos, neg, neu}; we average
mapped to [-1, +1] then scale by a tanh count-bonus so a wall of 1 positive
headline doesn't outweigh 5 mixed ones. Spec §3.1 weight 0.10.

M4a: replaces the M1 `_search_recent` stub (returned []) with real headlines
and keyword sentiment. M4b can swap _classify_sentiment for an LLM-backed
scorer that uses the user's BYOK key (in yf_helpers._classify_sentiment).
"""
from __future__ import annotations

from datetime import datetime

import numpy as np

from alpha_agent.signals.base import SignalScore, safe_fetch
from alpha_agent.signals.yf_helpers import extract_news_items, get_ticker

_SENT_TO_FLOAT = {"pos": 1.0, "neg": -1.0, "neu": 0.0}


def _fetch(ticker: str, as_of: datetime) -> SignalScore:
    raw_news = get_ticker(ticker).news or []
    items = extract_news_items(raw_news, limit=5)

    if not items:
        return SignalScore(
            ticker=ticker, z=0.0,
            raw={"n": 0, "mean_sent": 0.0, "headlines": []},
            confidence=0.3, as_of=as_of, source="yfinance",
            error="no news in last fetch window",
        )

    sentiments = [_SENT_TO_FLOAT[it["sentiment"]] for it in items]
    mean_sent = float(np.mean(sentiments))
    count_bonus = float(np.tanh(len(items) / 5))
    z = float(np.clip(mean_sent * 2 * count_bonus, -3.0, 3.0))

    return SignalScore(
        ticker=ticker, z=z,
        raw={"n": len(items), "mean_sent": mean_sent, "headlines": items},
        confidence=0.65, as_of=as_of, source="yfinance", error=None,
    )


def fetch_signal(ticker: str, as_of: datetime) -> SignalScore:
    return safe_fetch(_fetch, ticker, as_of, source="yfinance")
