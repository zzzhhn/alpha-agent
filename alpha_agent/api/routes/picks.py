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
from alpha_agent.fusion.grades import grade_dimensions
from alpha_agent.fusion.grade_thresholds import get_dimension_thresholds
from alpha_agent.fusion.rating import calibrated_confidence, map_to_tier

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
    # B2 (2026-05-19): true when the no-trade band saved a tier flip today
    # (raw_tier differed from sticky rating). UI surfaces a small indicator
    # so the user knows hysteresis is currently absorbing wobble.
    tier_flip_today: bool = False
    # B8 (2026-05-19): per-dimension letter grades from breakdown z's so
    # the picks table can show A+/A/B/.../F at-a-glance per row.
    dimension_grades: dict[str, str] = {}


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
    mode: str = Query("short", pattern="^(short|long)$"),
    side: str = Query("long", pattern="^(long|short)$"),
) -> PicksResponse:
    """Return tickers ranked by composite score.

    `side` (P1-2 two-sided view): "long" (default) returns the top-N by
    composite DESC — the highest-conviction longs. "short" returns the
    bottom-N by composite ASC — the most bearish names (UW/SELL tier),
    which the default long view never surfaces because they rank at the
    bottom of the universe. Same data + same pipeline; only the sort
    direction + LIMIT slice differ.

    Unions two sources so the full ~557-ticker universe is reachable:
      - daily_signals_fast: the 15-min intraday pipeline (~100 tickers),
        full cards with stored rating + confidence.
      - daily_signals_slow: the daily pipeline (full universe). It stores
        only composite_partial + breakdown, so rating is derived via
        map_to_tier and confidence via compute_confidence from the
        breakdown z's. These rows are flagged partial=True.

    A ticker present in fast is taken from fast (fresher and complete).
    `search` does a case-insensitive substring match on the ticker.

    `mode` (Phase 2 dual-factor): "short" (default, 12d/60d momentum-vol,
    aligned with the rest of the short-window composite) or "long"
    (252d/126d academic Jegadeesh-Titman/Daniel-Moskowitz framework). When
    "long", the picks list is re-ranked in Python using factor.raw.z_long
    (populated by fast_intraday's universe-wide eval) instead of the stored
    short-mode composite. SQL ordering is unchanged; we re-sort in Python
    after the score swap. Rows without z_long (legacy / partial) keep their
    original composite under either mode.
    """
    import traceback
    try:
        pool = await get_db_pool()
        from alpha_agent.backtest.confidence_calibration import (
            apply_calibration,
            load_active_calibration,
        )
        cal_map = await load_active_calibration(pool)
        search_norm = search.strip().upper() if search and search.strip() else None
        # side=short surfaces the bottom of the ranking (most bearish). The
        # direction is a controlled literal derived from the pattern-validated
        # `side`, never raw user input, so the f-string interpolation is safe.
        score_dir = "ASC" if side == "short" else "DESC"
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
            f"""
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
            ORDER BY partial ASC, score {score_dir}
            LIMIT $1
            """,
            limit,
            search_norm,
        )
        if not rows:
            return PicksResponse(picks=[], as_of=None, stale=False)

        most_recent: datetime = max(r["fetched_at"] for r in rows)
        stale = (datetime.now(UTC) - most_recent) > timedelta(hours=_STALE_THRESHOLD_HOURS)

        # Universe-wide band breakpoints so each dimension is graded against its
        # own cross-sectional distribution (not the returned top-N subset).
        dim_thresholds = await get_dimension_thresholds(pool)

        cards: list[LeanCard] = []
        for r in rows:
            try:
                parsed_breakdown: dict = json.loads(r["breakdown"])
                breakdown_data: list[dict] = parsed_breakdown.get("breakdown", [])
                tier_flip_today: bool = bool(parsed_breakdown.get("tier_flip_today", False))
            except (TypeError, json.JSONDecodeError):
                breakdown_data = []
                tier_flip_today = False
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
                confidence = calibrated_confidence(z_values, cal_map)
            else:
                # Fast row: confidence was computed (raw) at write time by the
                # fast cron and stored. Re-apply the calibration map at read
                # time so the dominant fast path is calibrated too (the stored
                # value is a raw compute_confidence output, so this is the
                # intended single application, not double-calibration).
                rating = r["rating"] or "HOLD"
                confidence = apply_calibration(_safe_float(r["confidence"], 0.0), cal_map)
            # Phase 2 long-mode re-rank: when mode=="long", look up
            # factor.raw.z_long and re-compute the composite contribution.
            # Old factor contribution gets subtracted, new long-z contribution
            # added. rating is re-derived from the new score. Rows missing
            # z_long (legacy data before the dual-eval landed, or slow-only
            # partial rows where fast_intraday hasn't run yet) keep their
            # short-mode score unchanged so the UI never shows a "missing"
            # state during the rollout window.
            if mode == "long" and not is_partial:
                for entry in breakdown_data:
                    if entry.get("signal") != "factor":
                        continue
                    raw = entry.get("raw")
                    if not isinstance(raw, dict) or "z_long" not in raw:
                        break
                    new_z = _safe_float(raw.get("z_long"), 0.0)
                    old_z = _safe_float(entry.get("z"), 0.0)
                    w_eff = _safe_float(entry.get("weight_effective"), 0.0)
                    # Score delta from swapping factor contribution
                    score = score + w_eff * (new_z - old_z)
                    # Update the breakdown entry in-place so top_drivers/
                    # top_drags reflect the long-mode ranking and the UI
                    # AttributionTable shows the active factor.z value.
                    entry["z"] = new_z
                    entry["contribution"] = w_eff * new_z
                    rating = map_to_tier(score)
                    break

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
                    tier_flip_today=tier_flip_today,
                    dimension_grades=grade_dimensions(breakdown_data, dim_thresholds),
                )
            )

        # SQL ordered by short-mode composite; after long-mode swap the
        # short order is stale. Re-sort in Python (partial-last preserved),
        # respecting side: long = score DESC, short = score ASC.
        if mode == "long":
            if side == "short":
                cards.sort(key=lambda c: (c.partial, c.composite_score))
            else:
                cards.sort(key=lambda c: (c.partial, -c.composite_score))

        return PicksResponse(picks=cards, as_of=most_recent, stale=stale)
    except Exception as e:
        # Surface the real exception so we can diagnose instead of seeing
        # a generic 500. Stable shape: 500 with detail = type:msg.
        from fastapi import HTTPException
        raise HTTPException(
            status_code=500,
            detail=f"picks_lean failed: {type(e).__name__}: {e}\n{traceback.format_exc()[:1500]}",
        ) from e
