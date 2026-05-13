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


import asyncio

from fastapi.responses import StreamingResponse

from alpha_agent.llm.brief_streamer import stream_brief


class StreamBriefRequest(BaseModel):
    provider: Literal["openai", "anthropic", "kimi", "ollama"]
    api_key: str = Field(min_length=1, repr=False)
    model: str | None = None
    base_url: str | None = None


def _sse_format(event: dict) -> bytes:
    """Serialize one event as a single SSE `data:` line. Keep newline-
    delimited JSON inside the data field so the client parses
    deterministically."""
    return f"data: {json.dumps(event)}\n\n".encode("utf-8")


@router.post("/{ticker}/stream")
async def post_brief_stream(
    payload: StreamBriefRequest,
    ticker: str = Path(min_length=1, max_length=10),
) -> StreamingResponse:
    """SSE-streaming Rich brief. Client posts with BYOK key in body."""
    ticker = ticker.upper()
    pool = await get_db_pool()
    row = await pool.fetchrow(
        "SELECT ticker, rating, composite, breakdown, fetched_at "
        "FROM daily_signals_fast WHERE ticker = $1 "
        "ORDER BY fetched_at DESC LIMIT 1",
        ticker,
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"No rating for {ticker}")

    breakdown: list[dict] = json.loads(row["breakdown"]).get("breakdown", [])
    composite = float(row["composite"]) if row["composite"] is not None else 0.0
    rating = row["rating"] or "HOLD"

    async def generator():
        try:
            async for event in stream_brief(
                provider=payload.provider,
                api_key=payload.api_key,
                ticker=ticker,
                rating=rating,
                composite=composite,
                breakdown=breakdown,
                model=payload.model,
                base_url=payload.base_url,
            ):
                yield _sse_format(event)
                # tiny await so the runtime flushes
                await asyncio.sleep(0)
        except Exception as e:
            # Sanitize: never echo the api_key. type(e).__name__ + str(e) is
            # enough for the client to act on (429, auth, etc.).
            yield _sse_format({
                "type": "error",
                "message": f"{type(e).__name__}: {str(e)[:200]}",
            })

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-store",
            "X-Accel-Buffering": "no",  # nginx; harmless on Vercel
        },
    )
