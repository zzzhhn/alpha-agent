"""political_impact signal: per-ticker macro events impact via LLM-as-Judge.

Sources rows from macro_events WHERE the ticker appears in tickers_extracted
(populated by Phase 5 LLM enrichment). Uses the same Tetlock-style
aggregation as news signal but over a 7-day window (macro events have
longer market half-life than daily ticker news).

Disambiguated from existing macro signal (VIX / sector ETF) in UI:
  this signal -> displayed as "Political"
  existing macro -> displayed as "Macro (Vol)"

Methodology (Phase 6a spec):
1. For each macro_events row in last 7d that lists the ticker in
   tickers_extracted:
   - If row has impact_bucket and direction_bucket set (LLM enriched),
     use them directly.
   - Else, fall back to Loughran-McDonald financial dictionary on
     title + " " + body, mapping pos/neg/neu to a single bucket triple.
2. Aggregate into Tetlock-style score:
     mean_sent = sum(impact_weight * direction_sign) / n
3. Confidence:
     0.7 if all rows have LLM bucket tags
     0.5 if some LLM and some LM fallback
     0.3 if pure LM fallback or zero events

Citation: Wagner-Zeckhauser-Ziegler (2018) JFE for political-event impact
on individual stock returns; Tetlock (2007) for the discrete-bucket
weighting; Loughran-McDonald (2011) for the dictionary fallback.
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


async def compute_political_impact_signal(ticker: str) -> dict[str, Any]:
    """Async core: query macro_events, apply LLM-as-Judge + LM fallback,
    return a SignalScore-shaped dict.

    Exposed as a separate async coroutine so tests can monkeypatch
    _query_recent_macro cleanly without spinning up an event loop in the
    sync wrapper.
    """
    items = await _query_recent_macro(ticker.upper())
    as_of = datetime.now(UTC)

    if not items:
        return SignalScore(
            ticker=ticker.upper(),
            z=0.0,
            raw={"n": 0, "mean_sent": 0.0, "events": []},
            confidence=0.3,
            as_of=as_of,
            source="macro_events",
            error="no macro events in last 7d",
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
        raw={"n": n, "mean_sent": float(mean_sent), "events": events_out[:10]},
        confidence=confidence,
        as_of=as_of,
        source="macro_events",
        error=None,
    )


def _fetch(ticker: str, as_of: datetime) -> SignalScore:
    """Sync wrapper around compute_political_impact_signal for the registry.

    safe_fetch (in fetch_signal below) catches the network/DB errors
    listed in signals.base._EXTERNAL_ERRORS; programming bugs propagate.

    NOTE: only safe to call from a sync parent context (e.g. build_card.py
    CLI). Async parent contexts (api/cron/fast_intraday._per_ticker) must
    use afetch_signal below to avoid 'asyncio.run() cannot be called from
    a running event loop' RuntimeError.
    """
    out = asyncio.run(compute_political_impact_signal(ticker.upper()))
    # asyncio.run returns a dict; ensure as_of reflects the caller's clock
    # for cron-shard consistency.
    out["as_of"] = as_of
    return out


def fetch_signal(ticker: str, as_of: datetime) -> SignalScore:
    return safe_fetch(_fetch, ticker, as_of, source="macro_events")


async def afetch_signal(ticker: str, as_of: datetime) -> SignalScore:
    """Async-native variant for async parent contexts (cron handlers).
    Bypasses asyncio.run() in _fetch which raises when a parent loop is
    already running. Same SignalScore output shape as fetch_signal."""
    try:
        out = await compute_political_impact_signal(ticker.upper())
    except Exception as e:  # noqa: BLE001 - mirror safe_fetch surface
        return SignalScore(
            ticker=ticker, z=0.0, raw=None, confidence=0.0,
            as_of=as_of, source="macro_events",
            error=f"{type(e).__name__}: {str(e)[:120]}",
        )
    out["as_of"] = as_of
    return out
