"""News-flow signal sourced from news_items (was: yfinance Ticker.news).

Queries the last 24h of news_items for the ticker, averages the LLM
sentiment_score, applies the same tanh count bonus the legacy module
used. Returns the same SignalScore shape so combine() and the
NewsBlock breakdown contract are unchanged.
"""
from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np

from alpha_agent.signals.base import SignalScore, safe_fetch
from alpha_agent.storage.postgres import get_pool


def _fetch(ticker: str, as_of: datetime) -> SignalScore:
    # Sync wrapper around the async pool query so the rest of the
    # signal pipeline (which is sync per-signal) does not need to learn
    # about async. The pool itself is reused across calls.
    items = asyncio.run(_query_recent_news(ticker.upper()))
    if not items:
        return SignalScore(
            ticker=ticker, z=0.0,
            raw={"n": 0, "mean_sent": 0.0, "headlines": []},
            confidence=0.3, as_of=as_of, source="news_items",
            error="no news in last 24h",
        )
    scored = [it for it in items if it.get("sentiment_score") is not None]
    if not scored:
        return SignalScore(
            ticker=ticker, z=0.0,
            raw={"n": len(items), "mean_sent": 0.0,
                 "headlines": _to_headlines(items)},
            confidence=0.4, as_of=as_of, source="news_items",
            error="no LLM-scored rows yet",
        )
    mean_sent = float(np.mean([it["sentiment_score"] for it in scored]))
    count_bonus = float(np.tanh(len(scored) / 5))
    z = float(np.clip(mean_sent * 2 * count_bonus, -3.0, 3.0))
    return SignalScore(
        ticker=ticker, z=z,
        raw={"n": len(items), "mean_sent": mean_sent,
             "headlines": _to_headlines(items)},
        confidence=0.7, as_of=as_of, source="news_items", error=None,
    )


def _to_headlines(items):
    """Match legacy NewsBlock decoder shape: [{title, publisher, published_at,
    link, sentiment}]."""
    label_map = {None: "neu", "pos": "pos", "neg": "neg", "neu": "neu"}
    return [
        {
            "title": it["headline"],
            "publisher": it["source"],
            "published_at": it["published_at"].isoformat()
                if hasattr(it["published_at"], "isoformat") else it["published_at"],
            "link": it["url"],
            "sentiment": label_map.get(it.get("sentiment_label"), "neu"),
        }
        for it in items[:10]
    ]


async def _query_recent_news(ticker: str) -> list[dict]:
    pool = await get_pool(os.environ["DATABASE_URL"])
    since = datetime.now(UTC) - timedelta(hours=24)
    rows = await pool.fetch(
        """
        SELECT headline, source, url, published_at,
               sentiment_score, sentiment_label
        FROM news_items
        WHERE ticker = $1 AND published_at > $2
        ORDER BY published_at DESC LIMIT 20
        """,
        ticker, since,
    )
    return [dict(r) for r in rows]


def fetch_signal(ticker: str, as_of: datetime) -> SignalScore:
    return safe_fetch(_fetch, ticker, as_of, source="news_items")
