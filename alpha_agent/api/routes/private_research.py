"""Operator-only experiments; reading a dashboard never polls providers or trades."""

from typing import Literal

from fastapi import APIRouter, Depends, Query, Response

from alpha_agent.api.dependencies import get_db_pool
from alpha_agent.auth.dependencies import require_admin

router = APIRouter(
    prefix="/api/research", tags=["private-research"], dependencies=[Depends(require_admin)]
)


@router.get("/option-observations")
async def option_samples(
    response: Response,
    symbol: Literal["SPY", "QQQ", "NVDA"] = "NVDA",
    limit: int = Query(1, ge=1, le=24),
):
    from alpha_agent.data.option_observatory import read_options

    response.headers["Cache-Control"] = "private, no-store"
    return await read_options(await get_db_pool(), symbol, limit)


@router.get("/event-shadow")
async def event_shadow(response: Response, limit: int = Query(10, ge=1, le=30)):
    from alpha_agent.paper.event_shadow import read_event_shadow
    from alpha_agent.paper.event_shadow_review import review_gate

    response.headers["Cache-Control"] = "private, no-store"
    pool = await get_db_pool()
    return {**await read_event_shadow(pool, limit=limit), "review": await review_gate(pool)}
