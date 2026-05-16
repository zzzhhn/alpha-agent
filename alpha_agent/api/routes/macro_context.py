"""GET /api/macro_context?ticker=X&limit=5

Returns macro events whose tickers_extracted (LLM-derived) contains the
ticker, ordered by published_at DESC. Lookback: 7 days.

Public endpoint, no auth (matches /api/picks, /api/stock).
"""
from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel

from alpha_agent.api.dependencies import get_db_pool

router = APIRouter(prefix="/api/macro_context", tags=["news"])


class MacroContextItem(BaseModel):
    id: int
    author: str | None
    title: str
    url: str | None
    body_excerpt: str | None
    published_at: str
    sentiment_score: float | None
    tickers_extracted: list[str]
    sectors_extracted: list[str]


class MacroContextResponse(BaseModel):
    items: list[MacroContextItem]


@router.get("", response_model=MacroContextResponse)
async def macro_context(
    ticker: str = Query(..., min_length=1, max_length=10),
    limit: int = Query(5, ge=1, le=20),
) -> MacroContextResponse:
    pool = await get_db_pool()
    rows = await pool.fetch(
        """
        SELECT id, author, title, url, body, published_at,
               sentiment_score, tickers_extracted, sectors_extracted
        FROM macro_events
        WHERE $1 = ANY(tickers_extracted)
          AND published_at > now() - interval '7 days'
        ORDER BY published_at DESC
        LIMIT $2
        """,
        ticker.upper(), limit,
    )
    items = []
    for r in rows:
        items.append(MacroContextItem(
            id=r["id"],
            author=r["author"],
            title=r["title"],
            url=r["url"],
            body_excerpt=(r["body"] or "")[:200],
            published_at=r["published_at"].isoformat(),
            sentiment_score=r["sentiment_score"],
            tickers_extracted=list(r["tickers_extracted"] or []),
            sectors_extracted=list(r["sectors_extracted"] or []),
        ))
    return MacroContextResponse(items=items)
