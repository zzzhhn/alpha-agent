"""News-flow signal: LLM-as-Judge 12-bucket + LM dictionary fallback.

Methodology (Phase 6a spec):
1. For each news_items row in last 24h for the ticker:
   - If row has impact_bucket and direction_bucket set (LLM enriched
     via Phase 5b read-time path), use them directly.
   - Else, fall back to Loughran-McDonald financial dictionary on the
     headline, mapping pos/neg/neu to a single bucket triple.
2. Aggregate into Tetlock-style score (Tetlock 2007):
     mean_sent = sum(impact_weight * direction_sign) / n
   with impact_weight in {none:0, low:0.3, medium:0.7, high:1.0}
   and  direction_sign in {bullish:+1, bearish:-1, neutral:0}.
3. Confidence:
     0.7 if all rows have LLM bucket tags
     0.5 if some LLM and some LM fallback
     0.3 if pure LM fallback or zero news

Backward compat:
- SignalScore.raw schema is {n, mean_sent, headlines} so combine.py and
  the frontend NewsBlock decoder still work. Semantics of mean_sent
  change from "avg LLM score" to "Tetlock-weighted bucket score".
- Public sync entry stays fetch_signal(ticker, as_of) per signals.base
  contract; used by cli/build_card.py registry.

Citations: Tetlock (2007) JoF for discrete-bucket weighting;
Loughran-McDonald (2011) JoF for the financial dictionary fallback.
"""
from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from typing import Any

from alpha_agent.news.lm_dictionary import score_text
from alpha_agent.signals.base import SignalScore, safe_fetch
from alpha_agent.storage.postgres import get_pool


_IMPACT_WEIGHT = {"none": 0.0, "low": 0.3, "medium": 0.7, "high": 1.0}
_DIRECTION_SIGN = {"bullish": 1, "bearish": -1, "neutral": 0}
_LM_TO_BUCKETS = {
    "bullish": ("medium", "bullish"),
    "bearish": ("medium", "bearish"),
    "neutral": ("low", "neutral"),
}


async def _query_recent_news(ticker: str) -> list[dict]:
    pool = await get_pool(os.environ["DATABASE_URL"])
    rows = await pool.fetch(
        """
        SELECT id, ticker, headline, source, url, published_at,
               impact_bucket, direction_bucket, sentiment_score
        FROM news_items
        WHERE ticker = $1
          AND published_at > now() - interval '24 hours'
        ORDER BY published_at DESC
        LIMIT 50
        """,
        ticker.upper(),
    )
    return [dict(r) for r in rows]


def _direction_to_label(direction: str) -> str:
    if direction == "bullish":
        return "pos"
    if direction == "bearish":
        return "neg"
    return "neu"


async def compute_news_signal(ticker: str) -> dict[str, Any]:
    """Async core: query news_items, apply LLM-as-Judge + LM fallback,
    return a SignalScore-shaped dict.

    Exposed as a separate async coroutine so tests can monkeypatch
    _query_recent_news cleanly without spinning up an event loop in the
    sync wrapper.
    """
    items = await _query_recent_news(ticker.upper())
    as_of = datetime.now(UTC)

    if not items:
        return SignalScore(
            ticker=ticker.upper(),
            z=0.0,
            raw={"n": 0, "mean_sent": 0.0, "headlines": []},
            confidence=0.3,
            as_of=as_of,
            source="news_items",
            error="no news in last 24h",
        )

    llm_count = 0
    lm_count = 0
    weighted_sum = 0.0
    headlines: list[dict] = []

    for it in items:
        impact = it.get("impact_bucket")
        direction = it.get("direction_bucket")
        if impact in _IMPACT_WEIGHT and direction in _DIRECTION_SIGN:
            llm_count += 1
        else:
            lm_label = score_text(it.get("headline") or "")
            impact, direction = _LM_TO_BUCKETS[lm_label]
            lm_count += 1
        weighted_sum += _IMPACT_WEIGHT[impact] * _DIRECTION_SIGN[direction]
        published = it.get("published_at")
        headlines.append({
            "title": it.get("headline"),
            "publisher": it.get("source") or "",
            "published_at": (
                published.isoformat()
                if hasattr(published, "isoformat") else str(published)
            ),
            "link": it.get("url") or "",
            "sentiment": _direction_to_label(direction),
        })

    n = len(items)
    mean_sent = weighted_sum / n
    if llm_count == n:
        confidence = 0.7
    elif llm_count > 0:
        confidence = 0.5
    else:
        confidence = 0.3

    z = float(max(-3.0, min(3.0, mean_sent * 2)))

    return SignalScore(
        ticker=ticker.upper(),
        z=z,
        raw={"n": n, "mean_sent": float(mean_sent), "headlines": headlines[:10]},
        confidence=confidence,
        as_of=as_of,
        source="news_items",
        error=None,
    )


def _fetch(ticker: str, as_of: datetime) -> SignalScore:
    """Sync wrapper around compute_news_signal for the signal registry.

    safe_fetch (in fetch_signal below) catches the network/DB errors
    listed in signals.base._EXTERNAL_ERRORS; programming bugs propagate.
    """
    out = asyncio.run(compute_news_signal(ticker.upper()))
    # asyncio.run returns a dict; ensure as_of reflects the caller's clock
    # for cron-shard consistency (compute_news_signal stamps now(UTC) too,
    # but the cron's as_of wins for deterministic backtests).
    out["as_of"] = as_of
    return out


def fetch_signal(ticker: str, as_of: datetime) -> SignalScore:
    return safe_fetch(_fetch, ticker, as_of, source="news_items")
