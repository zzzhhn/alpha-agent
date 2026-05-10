"""POST /api/brief/{ticker} — Lean rule-based thesis (Rich/LLM is M3 stub).

Lean mode builds a bull/bear thesis from top_drivers and top_drags without
any LLM call.  Rich (BYOK) mode is deferred to M3 and returns 501 here.
Spec §3.4.
"""
from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, HTTPException, Path
from pydantic import BaseModel, Field

from alpha_agent.api.dependencies import get_db_pool
from alpha_agent.fusion.attribution import top_drivers, top_drags

router = APIRouter(prefix="/api/brief", tags=["brief"])


class BriefRequest(BaseModel):
    mode: Literal["lean", "rich"] = "lean"
    llm_provider: str | None = None
    api_key: str | None = Field(default=None, repr=False)


class Thesis(BaseModel):
    bull: list[str]
    bear: list[str]


class BriefResponse(BaseModel):
    ticker: str
    rating: str
    thesis: Thesis
    rendered_at: str


def _render_lean_thesis(rating: str, breakdown: list[dict]) -> Thesis:
    drivers = top_drivers(breakdown, n=3)
    drags = top_drags(breakdown, n=3)

    def _z(signal: str) -> float:
        for b in breakdown:
            if b.get("signal") == signal:
                return b.get("z", 0.0)
        return 0.0

    bull = [
        f"{d.upper()} signal contributing positively (z={_z(d):+.2f})"
        for d in drivers
    ]
    bear = [
        f"{d.upper()} signal pulling negatively (z={_z(d):+.2f})"
        for d in drags
    ]
    if not bull:
        bull = ["No strongly positive signals detected"]
    if not bear:
        bear = ["No strongly negative signals detected"]
    return Thesis(bull=bull, bear=bear)


@router.post("/{ticker}", response_model=BriefResponse)
async def post_brief(
    payload: BriefRequest,
    ticker: str = Path(min_length=1, max_length=10),
) -> BriefResponse:
    """Generate a Lean thesis.  Rich mode returns 501 until M3."""
    if payload.mode == "rich":
        raise HTTPException(
            status_code=501,
            detail="Rich BYOK LLM brief not implemented in M2 (deferred to M3)",
        )

    ticker = ticker.upper()
    pool = await get_db_pool()
    row = await pool.fetchrow(
        "SELECT rating, breakdown, fetched_at FROM daily_signals_fast "
        "WHERE ticker = $1 ORDER BY fetched_at DESC LIMIT 1",
        ticker,
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"No rating for {ticker}")

    breakdown: list[dict] = json.loads(row["breakdown"]).get("breakdown", [])
    thesis = _render_lean_thesis(row["rating"], breakdown)
    return BriefResponse(
        ticker=ticker,
        rating=row["rating"],
        thesis=thesis,
        rendered_at=row["fetched_at"].isoformat(),
    )
