"""geopolitical_impact signal: macro_events filtered to geopolitical category.

A3 (2026-05-19) Phase 3 backlog split. Source: synthesizer T6 polish +
memory feedback_us_equity_news_political_signal — tariff / Fed /
sanctions / regulatory ACTIONS are the dominant short-term US-equity
movers in the 2025-26 cycle and deserve their own attribution lane
distinct from politician quotes / campaign-cycle content (which now
flows to sibling political_impact only).

Methodology mirrors political_impact (same Tetlock-style discrete-bucket
aggregation + LLM-as-Judge primary, LM-dictionary fallback):
1. Query macro_events 7d window for rows where ticker appears in
   tickers_extracted (LLM-enriched from the news pipeline).
2. Apply event_classifier — keep only category == 'geopolitical'.
3. Aggregate impact * direction across kept rows.
4. Confidence: 0.7 all-LLM, 0.5 mixed LLM+LM, 0.3 pure LM / empty.

Academic anchors (added 2026-05-19, mirrors political_impact set):
- Baker, Bloom, Davis (2016, QJE 131(4)) "Measuring Economic Policy
  Uncertainty" — EPU index, Fed/IMF/BIS standard.
- Hassan, Hollander, van Lent, Tahoun (2019, QJE 134(4)) "Firm-Level
  Political Risk: Measurement and Effects".
- Manela & Moreira (2017, JFE 123(1)) "News Implied Volatility and
  Disaster Concerns" (NVIX tail-risk).
- Wagner-Zeckhauser-Ziegler (2018, JFE) political-event impact on
  individual stock returns.

Phase X TBD: separate beta-to-EPU vs beta-to-VIX regression terms so
the user can attribute the move to monetary-uncertainty vs equity-
uncertainty channels.
"""
from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from typing import Any

from alpha_agent.news.event_classifier import classify_event
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


async def _query_recent_macro(ticker: str) -> list[dict]:
    pool = await get_pool(os.environ["DATABASE_URL"])
    rows = await pool.fetch(
        """
        SELECT id, title, body, author, impact_bucket, direction_bucket,
               sentiment_score, url, published_at
        FROM macro_events
        WHERE $1 = ANY(tickers_extracted)
          AND published_at > now() - interval '7 days'
        ORDER BY published_at DESC
        LIMIT 30
        """,
        ticker.upper(),
    )
    return [dict(r) for r in rows]


async def compute_geopolitical_impact_signal(ticker: str) -> dict[str, Any]:
    """Async core: query macro_events, filter to geopolitical category,
    apply LLM-as-Judge + LM fallback, return a SignalScore-shaped dict."""
    all_items = await _query_recent_macro(ticker.upper())
    items = [
        it for it in all_items
        if classify_event(it.get("author"), it.get("title"), it.get("body")) == "geopolitical"
    ]
    as_of = datetime.now(UTC)

    if not items:
        return SignalScore(
            ticker=ticker.upper(),
            z=0.0,
            raw={"n": 0, "mean_sent": 0.0, "events": [], "category": "geopolitical"},
            confidence=0.3,
            as_of=as_of,
            source="macro_events",
            error="no geopolitical events in last 7d",
        )

    llm_count = 0
    lm_count = 0
    weighted_sum = 0.0
    events_out: list[dict] = []

    for it in items:
        impact = it.get("impact_bucket")
        direction = it.get("direction_bucket")
        if impact in _IMPACT_WEIGHT and direction in _DIRECTION_SIGN:
            llm_count += 1
        else:
            lm_text = f"{it.get('title') or ''} {it.get('body') or ''}"
            lm_label = score_text(lm_text)
            impact, direction = _LM_TO_BUCKETS[lm_label]
            lm_count += 1
        weighted_sum += _IMPACT_WEIGHT[impact] * _DIRECTION_SIGN[direction]
        published = it.get("published_at")
        events_out.append({
            "title": it.get("title"),
            "author": it.get("author") or "",
            "published_at": (
                published.isoformat()
                if hasattr(published, "isoformat") else str(published)
            ),
            "url": it.get("url") or "",
            "direction": direction,
            "impact": impact,
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
        raw={"n": n, "mean_sent": float(mean_sent),
             "events": events_out[:10], "category": "geopolitical"},
        confidence=confidence,
        as_of=as_of,
        source="macro_events",
        error=None,
    )


def _fetch(ticker: str, as_of: datetime) -> SignalScore:
    """Sync wrapper around compute_geopolitical_impact_signal. Same
    caveats as political_impact._fetch: async parent contexts MUST
    use afetch_signal to dodge asyncio.run() in a running loop."""
    out = asyncio.run(compute_geopolitical_impact_signal(ticker.upper()))
    out["as_of"] = as_of
    return out


def fetch_signal(ticker: str, as_of: datetime) -> SignalScore:
    return safe_fetch(_fetch, ticker, as_of, source="macro_events")


async def afetch_signal(ticker: str, as_of: datetime) -> SignalScore:
    """Async-native variant for cron handlers."""
    try:
        out = await compute_geopolitical_impact_signal(ticker.upper())
    except Exception as e:  # noqa: BLE001 - mirror safe_fetch surface
        return SignalScore(
            ticker=ticker, z=0.0, raw=None, confidence=0.0,
            as_of=as_of, source="macro_events",
            error=f"{type(e).__name__}: {str(e)[:120]}",
        )
    out["as_of"] = as_of
    return out
