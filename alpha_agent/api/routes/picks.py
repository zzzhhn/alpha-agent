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


def _safe_float(v: float | None, default: float = 0.0) -> float:
    """NaN/Inf/None → default. PG DOUBLE PRECISION columns can hold NaN
    if cron wrote it; Pydantic + JSON serialization both choke on NaN."""
    import math
    if v is None:
        return default
    try:
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (TypeError, ValueError):
        return default


@router.get("/lean", response_model=PicksResponse)
async def picks_lean(limit: int = Query(20, ge=1, le=200)) -> PicksResponse:
    """Return top *limit* tickers sorted by composite_score DESC."""
    import traceback
    try:
        pool = await get_db_pool()
        # CTE pattern: first reduce to one row per ticker (latest date), then
        # rank by composite. Without the DISTINCT ON, tickers that have rows
        # on multiple dates surface as duplicates in the response.
        rows = await pool.fetch(
            """
            WITH latest AS (
                SELECT DISTINCT ON (ticker)
                    ticker, date, composite, rating, confidence, breakdown, fetched_at
                FROM daily_signals_fast
                WHERE composite IS NOT NULL AND composite = composite  -- exclude NaN
                ORDER BY ticker, date DESC, fetched_at DESC
            )
            SELECT ticker, date, composite, rating, confidence, breakdown, fetched_at
            FROM latest
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
            try:
                breakdown_data: list[dict] = json.loads(r["breakdown"]).get("breakdown", [])
            except (TypeError, json.JSONDecodeError):
                breakdown_data = []
            cards.append(
                LeanCard(
                    ticker=r["ticker"],
                    rating=r["rating"] or "HOLD",
                    confidence=_safe_float(r["confidence"], 0.0),
                    composite_score=_safe_float(r["composite"], 0.0),
                    as_of=r["fetched_at"].isoformat(),
                    top_drivers=top_drivers(breakdown_data),
                    top_drags=top_drags(breakdown_data),
                )
            )

        return PicksResponse(picks=cards, as_of=most_recent, stale=stale)
    except Exception as e:
        # Surface the real exception so we can diagnose instead of seeing
        # a generic 500. Stable shape: 500 with detail = type:msg.
        from fastapi import HTTPException
        raise HTTPException(
            status_code=500,
            detail=f"picks_lean failed: {type(e).__name__}: {e}\n{traceback.format_exc()[:1500]}",
        ) from e
