"""GET /api/watchlist + POST /api/watchlist (replace).

Auth required. Backs the dual-write watchlist sync: the frontend keeps
localStorage as the source of truth, and on every mutation best-effort
POSTs the full normalized list here so the fast_intraday cron (which
unions user_watchlist into its universe at offset=0) can pull intraday
signals for a user's starred tickers (e.g. NVDA).

POST has replace-semantics, not append: the client always sends the full
list, so the backend transactionally wipes the user's prior rows and
inserts the new set. Idempotent.
"""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from alpha_agent.api.dependencies import get_db_pool
from alpha_agent.auth.dependencies import require_user

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])

# Cap is conservative: a personal-scale user does not curate hundreds of
# names, and an unbounded list could blow the fast cron's offset=0 shard
# time budget. Invalid / duplicate entries are dropped silently below.
_MAX_TICKERS = 100
_TICKER_RE = re.compile(r"^[A-Z]{1,5}$")


class WatchlistResponse(BaseModel):
    tickers: list[str]


class WatchlistPut(BaseModel):
    tickers: list[str] = Field(..., max_length=_MAX_TICKERS)


@router.get("", response_model=WatchlistResponse)
async def list_watchlist(
    user_id: int = Depends(require_user),
) -> WatchlistResponse:
    """Return the calling user's stored tickers, oldest-first."""
    pool = await get_db_pool()
    rows = await pool.fetch(
        "SELECT ticker FROM user_watchlist WHERE user_id = $1 "
        "ORDER BY added_at, ticker",
        user_id,
    )
    return WatchlistResponse(tickers=[r["ticker"] for r in rows])


@router.post("", response_model=WatchlistResponse)
async def replace_watchlist(
    payload: WatchlistPut,
    user_id: int = Depends(require_user),
) -> WatchlistResponse:
    """Replace the user's watchlist with `tickers` exactly.

    Each ticker is upper-cased, deduped, and validated against the 1-5
    uppercase-letter shape. Invalid entries are dropped silently rather
    than 422ing the whole call (localStorage already holds the truth, the
    backend copy is best-effort).
    """
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in payload.tickers:
        t = raw.strip().upper()
        if t and t not in seen and _TICKER_RE.match(t):
            cleaned.append(t)
            seen.add(t)
    if len(cleaned) > _MAX_TICKERS:
        raise HTTPException(
            status_code=400,
            detail=f"Watchlist exceeds {_MAX_TICKERS} tickers after dedup",
        )

    pool = await get_db_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "DELETE FROM user_watchlist WHERE user_id = $1", user_id
            )
            if cleaned:
                await conn.executemany(
                    "INSERT INTO user_watchlist (user_id, ticker) "
                    "VALUES ($1, $2)",
                    [(user_id, t) for t in cleaned],
                )
    return WatchlistResponse(tickers=cleaned)
