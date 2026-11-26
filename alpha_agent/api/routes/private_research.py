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


@router.get("/premarket-review")
async def premarket_review(response: Response, owner: int = Depends(require_admin)):
    from alpha_agent.paper.premarket_review import unpack

    response.headers["Cache-Control"] = "private, no-store"
    pool = await get_db_pool()
    rows = await pool.fetch(
        """SELECT session_date,stage,captured_at,payload
        FROM premarket_review WHERE user_id=$1 AND session_date=(
          SELECT max(session_date) FROM premarket_review WHERE user_id=$1)
        ORDER BY captured_at""",
        owner,
    )
    # Bounded summary of paired observations, not an annualized return or NAV.
    prior = await pool.fetch(
        """SELECT payload FROM premarket_review WHERE user_id=$1
        AND stage='evaluation' ORDER BY session_date DESC LIMIT 20""",
        owner,
    )
    paired = [unpack(r["payload"])["results"] for r in prior]
    stats = {}
    for stage in ("premarket", "open_review"):
        values = [
            s[stage]["delta_bps"] for s in paired if s.get(stage, {}).get("status") == "measured"
        ]
        stats[stage] = {
            "measured": len(values),
            "mean_bps": round(sum(values) / len(values), 3) if values else None,
        }
    return {
        "records": [dict(r, payload=unpack(r["payload"])) for r in rows],
        "summary": {"observed_closes": len(prior), "stages": stats},
    }
