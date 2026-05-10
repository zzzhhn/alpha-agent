"""GET /api/picks/lean — top N picks by composite_score, read-only from DB.

SLA: < 500ms p95.  No synchronous signal fetch on the request path.
Spec §7.2.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Query
from pydantic import BaseModel

from alpha_agent.api.dependencies import get_db_pool
from alpha_agent.fusion.attribution import top_drivers, top_drags

router = APIRouter(prefix="/api/picks", tags=["picks"])

_STALE_THRESHOLD_HOURS = 24


class LeanCard(BaseModel):
    """Lean projection of a fast-signal row — no heavy breakdown list."""

    ticker: str
    rating: str
    confidence: float
    composite_score: float
    as_of: str
    top_drivers: list[str]
    top_drags: list[str]


class PicksResponse(BaseModel):
    picks: list[LeanCard]
    as_of: datetime | None
    stale: bool


@router.get("/lean", response_model=PicksResponse)
async def picks_lean(limit: int = Query(20, ge=1, le=100)) -> PicksResponse:
    """Return top *limit* tickers sorted by composite_score DESC."""
    pool = await get_db_pool()
    rows = await pool.fetch(
        """
        SELECT ticker, date, composite, rating, confidence, breakdown, fetched_at
        FROM daily_signals_fast
        ORDER BY composite DESC
        LIMIT $1
        """,
        limit,
    )
    if not rows:
        return PicksResponse(picks=[], as_of=None, stale=False)

    most_recent: datetime = max(r["fetched_at"] for r in rows)
    stale = (datetime.now(UTC) - most_recent) > timedelta(hours=_STALE_THRESHOLD_HOURS)

    cards: list[LeanCard] = []
    for r in rows:
        breakdown_data: list[dict] = json.loads(r["breakdown"]).get("breakdown", [])
        cards.append(
            LeanCard(
                ticker=r["ticker"],
                rating=r["rating"],
                confidence=r["confidence"],
                composite_score=r["composite"],
                as_of=r["fetched_at"].isoformat(),
                top_drivers=top_drivers(breakdown_data),
                top_drags=top_drags(breakdown_data),
            )
        )

    return PicksResponse(picks=cards, as_of=most_recent, stale=stale)
