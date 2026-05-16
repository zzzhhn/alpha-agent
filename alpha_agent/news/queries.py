"""Persistence helpers for the news pipeline.

All writes go through ON CONFLICT (dedup_hash) DO NOTHING so re-fetching
the same story across cycles is idempotent. The LLM enrichment paths
use UPDATE not upsert so the dedup_hash uniqueness is preserved.
"""
from __future__ import annotations

import json
from typing import Any, Iterable

import asyncpg

from alpha_agent.news.types import MacroEvent, NewsItem


def _safe_jsonb(obj: Any) -> str:
    """Drop NaN/Inf which Postgres JSONB rejects (cf. queries.py::_json_safe)."""
    import math
    def walk(x):
        if isinstance(x, dict):
            return {k: walk(v) for k, v in x.items()}
        if isinstance(x, (list, tuple)):
            return [walk(v) for v in x]
        if isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
            return None
        return x
    return json.dumps(walk(obj), default=str)


async def upsert_news_items(
    pool: asyncpg.Pool, items: Iterable[NewsItem]
) -> int:
    """Returns number of rows actually inserted (ON CONFLICT-skipped rows
    are not counted)."""
    rows = list(items)
    if not rows:
        return 0
    sql = """
        INSERT INTO news_items
            (dedup_hash, ticker, source, source_id, headline, url,
             published_at, summary, raw)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb)
        ON CONFLICT (dedup_hash) DO NOTHING
    """
    inserted = 0
    async with pool.acquire() as conn:
        for it in rows:
            result = await conn.execute(
                sql,
                it.dedup(), it.ticker, it.source, it.source_id, it.headline,
                it.url, it.published_at, it.summary, _safe_jsonb(it.raw),
            )
            # asyncpg execute returns 'INSERT 0 N' where N is rows touched.
            if result.endswith(" 1"):
                inserted += 1
    return inserted


async def upsert_macro_events(
    pool: asyncpg.Pool, events: Iterable[MacroEvent]
) -> int:
    rows = list(events)
    if not rows:
        return 0
    sql = """
        INSERT INTO macro_events
            (dedup_hash, source, source_id, author, title, url, body,
             published_at, raw)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb)
        ON CONFLICT (dedup_hash) DO NOTHING
    """
    inserted = 0
    async with pool.acquire() as conn:
        for e in rows:
            result = await conn.execute(
                sql,
                e.dedup(), e.source, e.source_id, e.author, e.title, e.url,
                e.body, e.published_at, _safe_jsonb(e.raw),
            )
            if result.endswith(" 1"):
                inserted += 1
    return inserted


async def update_news_item_llm(
    pool: asyncpg.Pool, item_id: int,
    sentiment_score: float | None, sentiment_label: str | None,
) -> None:
    await pool.execute(
        "UPDATE news_items SET sentiment_score=$1, sentiment_label=$2, "
        "llm_processed_at=now() WHERE id=$3",
        sentiment_score, sentiment_label, item_id,
    )


async def update_macro_event_llm(
    pool: asyncpg.Pool, event_id: int,
    tickers: list[str], sectors: list[str], sentiment_score: float | None,
) -> None:
    await pool.execute(
        "UPDATE macro_events SET tickers_extracted=$1, sectors_extracted=$2, "
        "sentiment_score=$3, llm_processed_at=now() WHERE id=$4",
        tickers, sectors, sentiment_score, event_id,
    )
