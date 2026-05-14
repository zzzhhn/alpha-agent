"""POST /api/brief/{ticker} — Lean rule-based thesis (Rich/LLM is M3 stub).

Lean mode builds a bull/bear thesis from top_drivers and top_drags without
any LLM call.  Rich (BYOK) mode is deferred to M3 and returns 501 here.
Spec §3.4.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, Field

from alpha_agent.api.dependencies import get_db_pool
from alpha_agent.auth.crypto_box import CryptoError, decrypt
from alpha_agent.auth.dependencies import require_user
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
    # Phase 4: the BYOK key is no longer in the body - it is read
    # server-side from user_byok for the authenticated user. Only an
    # optional model override remains.
    model_override: str | None = None


def _sse_format(event: dict) -> bytes:
    """Serialize one event as a single SSE `data:` line. Keep newline-
    delimited JSON inside the data field so the client parses
    deterministically."""
    return f"data: {json.dumps(event)}\n\n".encode("utf-8")


@router.post("/{ticker}/stream")
async def post_brief_stream(
    payload: StreamBriefRequest,
    ticker: str = Path(min_length=1, max_length=10),
    user_id: int = Depends(require_user),
) -> StreamingResponse:
    """SSE-streaming Rich brief. Auth required; BYOK key fetched + decrypted
    server-side from the authenticated user's stored credentials."""
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

    byok = await pool.fetchrow(
        "SELECT provider, ciphertext, nonce, model, base_url "
        "FROM user_byok WHERE user_id = $1 LIMIT 1",
        user_id,
    )
    if byok is None:
        raise HTTPException(
            status_code=400, detail="No BYOK key set; visit /settings to add one"
        )

    master = os.environ.get("BYOK_MASTER_KEY")
    if not master:
        raise HTTPException(status_code=500, detail="BYOK_MASTER_KEY not configured")

    breakdown: list[dict] = json.loads(row["breakdown"]).get("breakdown", [])
    composite = float(row["composite"]) if row["composite"] is not None else 0.0
    rating = row["rating"] or "HOLD"

    async def generator():
        try:
            plaintext_key = decrypt(byok["ciphertext"], byok["nonce"], master.encode("utf-8"))
        except CryptoError:
            yield _sse_format({
                "type": "error",
                "message": "Stored key cannot be decrypted. Please re-save it in /settings.",
            })
            return
        try:
            async for event in stream_brief(
                provider=byok["provider"],
                api_key=plaintext_key,
                ticker=ticker,
                rating=rating,
                composite=composite,
                breakdown=breakdown,
                model=payload.model_override or byok["model"],
                base_url=byok["base_url"],
            ):
                yield _sse_format(event)
                await asyncio.sleep(0)
            # Stamp usage for the /settings "last used" display.
            await pool.execute(
                "UPDATE user_byok SET last_used_at = now() "
                "WHERE user_id = $1 AND provider = $2",
                user_id, byok["provider"],
            )
        except Exception as e:
            # Server-side observability: full error to stderr for Vercel logs.
            print(f"brief stream error: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
            # Client-facing message: safe generic text, no raw str(e) (key-leak risk).
            yield _sse_format({
                "type": "error",
                "message": f"LLM request failed ({type(e).__name__}). Check your key in /settings.",
            })

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
