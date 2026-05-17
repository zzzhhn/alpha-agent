"""BYOK-LLM batch enrichment for news_items + macro_events.

Runs as the news_llm_enrich cron. Picks `row_limit` (default 100) rows
with llm_processed_at IS NULL, batches them through LiteLLMClient
(batch size 15), parses the structured JSON response, writes back.

Error semantics per spec: NO row-level retry cap. A malformed LLM
response leaves the rows untouched so the next cron tick re-picks them.
Backlog visible via /api/_health/news_freshness.llm_backlog.

Cost guard: row_limit per cron run + max_tokens=2000 per LLM call.
"""
from __future__ import annotations

import json
import logging

from alpha_agent.llm.base import Message
from alpha_agent.news.queries import (
    update_macro_event_llm,
    update_news_item_llm,
)

logger = logging.getLogger(__name__)

_BATCH_SIZE = 15
_MAX_TOKENS = 2000

_NEWS_SYSTEM = (
    "You score per-ticker financial news sentiment. For each headline in "
    "the user message, return a JSON array element of shape "
    '{"id": <int>, "sentiment_score": <float in [-1,1]>, '
    '"sentiment_label": "pos"|"neg"|"neu"}. Be conservative: "company '
    'beats earnings" is +0.4 to +0.6, not 1.0. Use 1.0/-1.0 only for '
    "genuinely landmark events. Output the JSON array only, no prose."
)

_MACRO_SYSTEM = (
    "You analyze political/policy/geopolitical events for US-equity "
    "market impact. For each event in the user message, return a JSON "
    'array element of shape {"id": <int>, "tickers": [<US ticker>], '
    '"sectors": [<GICS sector name>], "sentiment_score": <float in [-1,1]>}. '
    "Tickers should be 1-15 max; leave empty for purely partisan posts. "
    "Apple-related posts include AAPL. Tariff announcements list relevant "
    "ADRs + sectors. Sanctions list directly affected names. Output the "
    "JSON array only, no prose."
)


def _build_llm_client():
    """Indirection so tests can monkeypatch _build_llm_client without
    pulling LiteLLM env into the test process."""
    from alpha_agent.config import get_settings
    from alpha_agent.llm.factory import create_llm_client
    return create_llm_client(get_settings())


async def enrich_pending(pool, row_limit: int = 100) -> tuple[int, int]:
    """Returns (n_processed, n_failed_batches)."""
    llm = _build_llm_client()
    n_proc = 0
    n_failed = 0

    # News items
    news = await pool.fetch(
        f"SELECT id, ticker, headline FROM news_items "
        f"WHERE llm_processed_at IS NULL "
        f"ORDER BY id LIMIT {int(row_limit)}"
    )
    for batch in _chunks(news, _BATCH_SIZE):
        ok = await _enrich_news_batch(pool, llm, batch)
        if ok:
            n_proc += len(batch)
        else:
            n_failed += 1

    # Macro events (separate row_limit budget would over-engineer; share)
    macro = await pool.fetch(
        f"SELECT id, title, body, author FROM macro_events "
        f"WHERE llm_processed_at IS NULL "
        f"ORDER BY id LIMIT {int(row_limit)}"
    )
    for batch in _chunks(macro, _BATCH_SIZE):
        ok = await _enrich_macro_batch(pool, llm, batch)
        if ok:
            n_proc += len(batch)
        else:
            n_failed += 1

    return n_proc, n_failed


async def enrich_news_for_ticker(
    pool, llm, ticker: str, row_limit: int = 100,
) -> tuple[int, int]:
    """BYOK per-ticker enrichment for the read-time path.

    Caller supplies the LLM client (typically built from the user's
    stored BYOK key via api.byok.get_llm_client). Only touches
    news_items rows WHERE ticker = $1 AND llm_processed_at IS NULL.
    Macro events use a separate dashboard-level enrich path (P1).

    Returns (n_processed, n_failed_batches). row_limit caps how many
    news_items a single user click can enqueue (token cost guard).
    """
    n_proc = 0
    n_failed = 0
    news = await pool.fetch(
        "SELECT id, ticker, headline FROM news_items "
        "WHERE ticker = $1 AND llm_processed_at IS NULL "
        "ORDER BY id LIMIT $2",
        ticker.upper(), int(row_limit),
    )
    for batch in _chunks(news, _BATCH_SIZE):
        ok = await _enrich_news_batch(pool, llm, batch)
        if ok:
            n_proc += len(batch)
        else:
            n_failed += 1
    return n_proc, n_failed


def _chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


async def _enrich_news_batch(pool, llm, batch) -> bool:
    user_payload = "\n".join(
        f'{{"id": {r["id"]}, "ticker": "{r["ticker"]}", '
        f'"headline": {json.dumps(r["headline"])}}}'
        for r in batch
    )
    messages = [
        Message(role="system", content=_NEWS_SYSTEM),
        Message(role="user", content=user_payload),
    ]
    try:
        resp = await llm.chat(messages, temperature=0.0, max_tokens=_MAX_TOKENS)
        parsed = json.loads(resp.content)
    except Exception as exc:
        logger.warning("news llm enrich batch failed: %s: %s",
                       type(exc).__name__, exc)
        return False
    by_id = {int(p["id"]): p for p in parsed if isinstance(p, dict) and "id" in p}
    for row in batch:
        p = by_id.get(int(row["id"]))
        if p is None:
            continue
        try:
            await update_news_item_llm(
                pool, int(row["id"]),
                float(p.get("sentiment_score")) if p.get("sentiment_score") is not None else None,
                p.get("sentiment_label"),
            )
        except Exception as exc:
            logger.warning("news llm update failed row=%s: %s: %s",
                           row["id"], type(exc).__name__, exc)
    return True


async def _enrich_macro_batch(pool, llm, batch) -> bool:
    user_payload = "\n".join(
        f'{{"id": {r["id"]}, "author": "{r["author"]}", '
        f'"title": {json.dumps(r["title"])}, '
        f'"body": {json.dumps((r["body"] or "")[:1500])}}}'
        for r in batch
    )
    messages = [
        Message(role="system", content=_MACRO_SYSTEM),
        Message(role="user", content=user_payload),
    ]
    try:
        resp = await llm.chat(messages, temperature=0.0, max_tokens=_MAX_TOKENS)
        parsed = json.loads(resp.content)
    except Exception as exc:
        logger.warning("macro llm enrich batch failed: %s: %s",
                       type(exc).__name__, exc)
        return False
    by_id = {int(p["id"]): p for p in parsed if isinstance(p, dict) and "id" in p}
    for row in batch:
        p = by_id.get(int(row["id"]))
        if p is None:
            continue
        try:
            await update_macro_event_llm(
                pool, int(row["id"]),
                list(p.get("tickers") or []),
                list(p.get("sectors") or []),
                float(p.get("sentiment_score")) if p.get("sentiment_score") is not None else None,
            )
        except Exception as exc:
            logger.warning("macro llm update failed row=%s: %s: %s",
                           row["id"], type(exc).__name__, exc)
    return True
