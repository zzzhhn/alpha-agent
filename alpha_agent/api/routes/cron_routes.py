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

from fastapi import APIRouter, Query

router = APIRouter(prefix="/api/cron", tags=["cron"])


@router.post("/slow_daily")
@router.get("/slow_daily")
async def slow_daily(
    limit: int | None = Query(None, ge=1, le=600),
    offset: int | None = Query(None, ge=0, le=600),
) -> dict[str, Any]:
    """Run slow_daily cron. `limit=N` caps universe (≤300s Hobby budget).
    `offset=M` starts at SP500_UNIVERSE[M]; combined with limit, enables
    GH-Actions multi-shot full SP500 coverage (e.g. 4 × {limit:140, offset:0/140/280/420}).
    """
    from api.cron.slow_daily import handler
    return await handler(limit=limit, offset=offset)


@router.post("/fast_intraday")
@router.get("/fast_intraday")
async def fast_intraday(
    limit: int | None = Query(None, ge=1, le=600),
    offset: int | None = Query(None, ge=0, le=600),
    tier: str = Query("full", pattern="^(full|tech|mid|slow)$"),
) -> dict[str, Any]:
    """Run fast_intraday cron. `limit=N` caps watchlist (Hobby 300s budget).
    `offset=M` starts at SP500_UNIVERSE[M]; combined with limit, enables
    multi-shot coverage of the top tickers.

    `tier`: which signal subset to refresh this run. full = all 10 modules
    (legacy bootstrap); tech / mid / slow refresh only their named subset
    and round-trip the rest from the previous breakdown (see
    api/cron/fast_intraday.py docstring for the schedule design).
    """
    from api.cron.fast_intraday import handler
    return await handler(limit=limit, offset=offset, tier=tier)


@router.post("/alert_dispatcher")
@router.get("/alert_dispatcher")
async def alert_dispatcher() -> dict[str, Any]:
    from api.cron.alert_dispatcher import handler
    return await handler()


@router.post("/news_per_ticker")
@router.get("/news_per_ticker")
async def cron_news_per_ticker(
    limit: int | None = Query(None, ge=1, le=600),
    offset: int | None = Query(None, ge=0, le=600),
) -> dict[str, Any]:
    """Walk SP500 + watchlist, call PerTickerAggregator, upsert
    news_items. Limit + offset enable multi-shot sharding."""
    from api.cron.news_pipeline import per_ticker_handler
    return await per_ticker_handler(limit=limit, offset=offset)


@router.post("/news_macro")
@router.get("/news_macro")
async def cron_news_macro() -> dict[str, Any]:
    """Parallel-poll Truth/Fed/OFAC, upsert macro_events."""
    from api.cron.news_pipeline import macro_handler
    return await macro_handler()


# news_llm_enrich cron route removed 2026-05-17.
# The previous cron-side handler called get_settings() -> create_llm_client()
# which requires a global LLM key in the server env. That violates BYOK
# (the platform deliberately does not hold a global key; each user supplies
# their own). Read-time replacement: POST /api/news/enrich/{ticker} with
# Depends(get_llm_client), which sources the caller's stored BYOK key.
