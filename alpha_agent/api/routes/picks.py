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
from alpha_agent.fusion.rating import compute_confidence, map_to_tier

router = APIRouter(prefix="/api/picks", tags=["picks"])

_STALE_THRESHOLD_HOURS = 24


class LeanCard(BaseModel):
    """Lean projection of a signal row, no heavy breakdown list.

    `partial` marks a slow-only row: it comes from daily_signals_slow,
    which stores composite_partial + breakdown but no rating/confidence,
    so those two are derived here. Partial rows exclude the fast factors
    and can be up to ~1 day old.
    """

    ticker: str
    rating: str
    confidence: float
    composite_score: float
    as_of: str
    top_drivers: list[str]
    top_drags: list[str]
    partial: bool = False


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
async def picks_lean(
    limit: int = Query(50, ge=1, le=600),
    search: str | None = Query(None, max_length=12),
) -> PicksResponse:
    """Return tickers sorted by composite score DESC.

    Unions two sources so the full ~557-ticker universe is reachable:
      - daily_signals_fast: the 15-min intraday pipeline (~100 tickers),
        full cards with stored rating + confidence.
      - daily_signals_slow: the daily pipeline (full universe). It stores
        only composite_partial + breakdown, so rating is derived via
        map_to_tier and confidence via compute_confidence from the
        breakdown z's. These rows are flagged partial=True.

    A ticker present in fast is taken from fast (fresher and complete).
    `search` does a case-insensitive substring match on the ticker.
    """
    import traceback
    try:
        pool = await get_db_pool()
        search_norm = search.strip().upper() if search and search.strip() else None
        # DISTINCT ON reduces each table to its latest row per ticker, then
        # UNION ALL stitches them with fast taking precedence (NOT EXISTS
        # drops slow rows whose ticker already came from fast). Dedup, the
        # search filter, sort, and limit all run in SQL so only the rows we
        # actually return get their breakdown JSON parsed below.
        #
        # ORDER BY partial ASC first: a slow-only composite_partial is not
        # on the same scale as a full fast composite, so real fast cards
        # must always outrank partial ones. Within each group, score DESC.
        # Net effect: the default top-N view stays all-real (240 fast
        # cards), partial rows only surface on search or a high limit.
        rows = await pool.fetch(
            """
            WITH fast_latest AS (
                SELECT DISTINCT ON (ticker)
                    ticker, composite AS score, rating,
                    confidence, breakdown, fetched_at, false AS partial
                FROM daily_signals_fast
                WHERE composite IS NOT NULL AND composite = composite
                ORDER BY ticker, date DESC, fetched_at DESC
            ),
            slow_latest AS (
                SELECT DISTINCT ON (ticker)
                    ticker, composite_partial AS score, NULL::text AS rating,
                    NULL::double precision AS confidence, breakdown,
                    fetched_at, true AS partial
                FROM daily_signals_slow
                WHERE composite_partial IS NOT NULL
                    AND composite_partial = composite_partial
                ORDER BY ticker, date DESC, fetched_at DESC
            ),
            combined AS (
                SELECT * FROM fast_latest
                UNION ALL
                SELECT * FROM slow_latest s
                WHERE NOT EXISTS (
                    SELECT 1 FROM fast_latest f WHERE f.ticker = s.ticker
                )
            )
            SELECT ticker, score, rating, confidence, breakdown,
                   fetched_at, partial
            FROM combined
            WHERE ($2::text IS NULL OR ticker ILIKE '%' || $2 || '%')
            ORDER BY partial ASC, score DESC
            LIMIT $1
            """,
            limit,
            search_norm,
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
            score = _safe_float(r["score"], 0.0)
            is_partial = bool(r["partial"])
            if is_partial:
                # Slow-only row: derive rating + confidence the same way the
                # fast cron does, from the partial composite + breakdown z's.
                rating = map_to_tier(score)
                z_values = [
                    z for e in breakdown_data
                    if isinstance((z := e.get("z")), (int, float))
                ]
                confidence = compute_confidence(z_values)
            else:
                rating = r["rating"] or "HOLD"
                confidence = _safe_float(r["confidence"], 0.0)
            cards.append(
                LeanCard(
                    ticker=r["ticker"],
                    rating=rating,
                    confidence=confidence,
                    composite_score=score,
                    as_of=r["fetched_at"].isoformat(),
                    top_drivers=top_drivers(breakdown_data),
                    top_drags=top_drags(breakdown_data),
                    partial=is_partial,
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
