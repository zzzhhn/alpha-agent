"""FastAPI cron endpoints (M2 fixup for Vercel deployment).

Background: M2 originally placed cron handlers at `api/cron/*.py` as standalone
Vercel serverless functions. They had a non-standard `async def handler() -> dict`
signature that Vercel's Python runtime can't invoke. Combined with the catchall
`/api/(.*)` rewrite forwarding every request to `api/index.py`, the cron files
were never reachable as deployed URLs.

Fix: expose 3 POST routes here that thin-wrap the M2 handlers. The existing
rewrite captures /api/cron/* and routes to FastAPI, which dispatches here.
Vercel cron config (vercel.json) keeps the same paths.

Each route returns the handler's dict directly (200 with {ok, ...}).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter

router = APIRouter(prefix="/api/cron", tags=["cron"])


@router.post("/slow_daily")
async def slow_daily() -> dict[str, Any]:
    from api.cron.slow_daily import handler
    return await handler()


@router.post("/fast_intraday")
async def fast_intraday() -> dict[str, Any]:
    from api.cron.fast_intraday import handler
    return await handler()


@router.post("/alert_dispatcher")
async def alert_dispatcher() -> dict[str, Any]:
    from api.cron.alert_dispatcher import handler
    return await handler()


# Vercel cron pings via GET on the path. Mirror each POST to GET so the
# scheduler can trigger without method mismatch.
@router.get("/slow_daily")
async def slow_daily_get() -> dict[str, Any]:
    from api.cron.slow_daily import handler
    return await handler()


@router.get("/fast_intraday")
async def fast_intraday_get() -> dict[str, Any]:
    from api.cron.fast_intraday import handler
    return await handler()


@router.get("/alert_dispatcher")
async def alert_dispatcher_get() -> dict[str, Any]:
    from api.cron.alert_dispatcher import handler
    return await handler()
