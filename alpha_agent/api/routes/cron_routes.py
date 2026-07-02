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

import json
import os
import time
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Query

from alpha_agent.storage.postgres import get_pool

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


@router.post("/l2_cycle")
@router.get("/l2_cycle")
async def l2_cycle() -> dict[str, Any]:
    """Advance the L2 paper book one step over the product ledger (generate ->
    fill -> mark any due rebalance). Idempotent; schedule daily after the close
    so l2_equity_daily accumulates a forward curve."""
    from api.cron.l2_cycle import handler
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


@router.post("/minute_bars")
@router.get("/minute_bars")
async def cron_minute_bars(
    limit: int = 75,
    offset: int = 0,
) -> dict[str, Any]:
    """Pull 1-min bars for a slice of the SP500 universe and stamp cron_runs.

    Sharded via limit/offset so a single Hobby invocation stays under the
    300s budget. Universe is read from daily_signals_slow (~557 tickers)
    and ordered alphabetically for deterministic slicing across shards.
    """
    from alpha_agent.data.minute_price import (
        prune_minute_bars,
        pull_and_store_minute_bars,
    )

    started_at = datetime.now(UTC)
    pool = await get_pool(os.environ["DATABASE_URL"])

    # Retention prune (first shard only, once per cycle): keep a rolling window
    # of MINUTE_BARS_RETENTION_DAYS. The Neon free-tier 512MB limit cannot hold
    # a 7-day window (~1.4M rows / ~324MB crowded out every other table and
    # produced DiskFullError on 2026-06-26), so the window is now 2 days. A
    # daily DELETE stabilizes the table at its high-water mark: plain VACUUM
    # does not shrink the file on Neon, but it marks pages reusable so new
    # inserts reuse them instead of extending the file.
    if offset == 0:
        await prune_minute_bars(pool)

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT DISTINCT ticker FROM daily_signals_slow ORDER BY ticker LIMIT $1 OFFSET $2",
            limit,
            offset,
        )
    tickers = [r["ticker"] for r in rows]

    total_rows = 0
    tickers_pulled = 0
    error_count = 0
    failed: list[dict[str, str]] = []
    for ticker in tickers:
        try:
            written = await pull_and_store_minute_bars(pool, ticker)
            total_rows += int(written or 0)
            tickers_pulled += 1
        except Exception as exc:
            error_count += 1
            if len(failed) < 20:
                failed.append({"ticker": ticker, "error": f"{type(exc).__name__}: {exc}"})

    details = json.dumps(
        {
            "tickers_pulled": tickers_pulled,
            "rows_written": total_rows,
            "offset": offset,
            "limit": limit,
            "error_count": error_count,
            "failed_tickers": failed,
        }
    )
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO cron_runs (cron_name, started_at, finished_at, ok, error_count, details) "
            "VALUES ('minute_bars_pull', $1, now(), true, $2, $3::jsonb)",
            started_at,
            error_count,
            details,
        )

    return {
        "ok": True,
        "tickers_pulled": tickers_pulled,
        "rows_written": total_rows,
        "offset": offset,
        "limit": limit,
        "error_count": error_count,
    }


@router.post("/daily_prices")
@router.get("/daily_prices")
async def cron_daily_prices(
    limit: int | None = Query(None, ge=1, le=600),
    offset: int | None = Query(None, ge=0, le=600),
    period: str = Query("5d"),
) -> dict[str, Any]:
    """Append daily closes for the universe into daily_prices (the
    forward-return source for the walk-forward IC engine). `period` defaults
    to the daily "5d" append; pass a longer period (e.g. 3y) over offset
    slices to backfill history from the production backend."""
    from api.cron.daily_prices import handler
    return await handler(limit=limit, offset=offset, period=period)


@router.post("/methodology_proposer")
@router.get("/methodology_proposer")
async def cron_methodology_proposer() -> dict[str, Any]:
    """Phase 2a: daily statistics-driven methodology proposer. Enumerates
    single-knob config candidates, validates each on purged walk-forward OOS
    folds with trial-count deflation, and queues survivors as pending
    config_change_log rows for human approval (Phase 2b). Stays dormant
    (proposes nothing) until enough daily_prices history accrues to validate.
    Nothing auto-applies."""
    from alpha_agent.evolution.proposer import run_proposer

    pool = await get_pool(os.environ["DATABASE_URL"])
    started_at = datetime.now(UTC)
    try:
        result = await run_proposer(pool)
    except Exception as exc:  # noqa: BLE001
        # A proposer failure must leave an ok=false row so it stays visible in
        # cron_runs (a swallowed failure would silently never propose).
        err = f"{type(exc).__name__}: {exc}"
        await pool.execute(
            "INSERT INTO cron_runs (cron_name, started_at, finished_at, ok, error_count, details) "
            "VALUES ($1, $2, now(), false, 1, $3::jsonb)",
            "methodology_proposer",
            started_at,
            json.dumps({"error": err}),
        )
        raise
    details = json.dumps(
        {
            "evaluated": result.get("evaluated", 0),
            "proposed": result.get("proposed", 0),
            "dormant": result.get("dormant", False),
        }
    )
    await pool.execute(
        "INSERT INTO cron_runs (cron_name, started_at, finished_at, ok, error_count, details) "
        "VALUES ($1, $2, now(), true, 0, $3::jsonb)",
        "methodology_proposer",
        started_at,
        details,
    )
    return {"ok": True, **result}


# Wall-clock budget for one runner invocation. Kept under Vercel's function
# limit so we mark_failed cleanly (a diagnosable terminal state) rather than
# getting hard-killed mid-run and leaving a job stuck 'running'. Only checked
# BETWEEN jobs, so a single in-flight job still runs to its natural length;
# this just stops the runner from starting a fresh job too late.
_RUN_PROPOSE_BUDGET_S = 230.0


@router.post("/run_propose_jobs")
@router.get("/run_propose_jobs")
async def cron_run_propose_jobs() -> dict[str, Any]:
    """Reliable execution path for the LLM factor proposer (the /evolution
    'propose factors' button).

    POST /api/factor-lab/propose only ENQUEUES a job. The old design ran the
    work in a FastAPI BackgroundTask after the 202 response, but Vercel freezes
    the function once the response is sent, so that task never completed and the
    button silently produced nothing after the 2026-05-26 async refactor. A
    GitHub Actions runner (triggered instantly on enqueue via workflow_dispatch,
    plus a fallback schedule) calls this endpoint instead; here the work runs
    INSIDE the request (server-to-server, no browser long-hold, completes within
    the function budget) so it always finishes and writes a terminal job state
    the frontend poll can read.

    Drains queued jobs oldest-first until the queue empties or the budget is
    hit. Each job's failure is persisted onto its row, never swallowed."""
    from alpha_agent.api.routes.factor_lab import _run_propose_work
    from alpha_agent.config_store import refresh_config
    from alpha_agent.evolution.diagnostics import compute_diagnostic
    from alpha_agent.storage import propose_jobs

    pool = await get_pool(os.environ["DATABASE_URL"])
    deadline = time.monotonic() + _RUN_PROPOSE_BUDGET_S
    drained: list[dict[str, Any]] = []
    while time.monotonic() < deadline:
        job = await propose_jobs.claim_oldest_queued(pool)
        if job is None:
            break
        job_id = job["id"]
        try:
            # Mirror post_propose's pre-work so the LLM sees the live baseline.
            await refresh_config(pool)
            diagnostic = await compute_diagnostic(pool)
            result = await _run_propose_work(
                pool, job["user_id"], job["n"], diagnostic
            )
            await propose_jobs.mark_done(pool, job_id, result)
            drained.append(
                {
                    "job_id": job_id,
                    "status": "done",
                    "proposed": result.get("proposed", 0),
                    "evaluated": result.get("evaluated", 0),
                }
            )
        except Exception as exc:  # noqa: BLE001 — terminal failure must be observable
            err = f"{type(exc).__name__}: {exc}"
            await propose_jobs.mark_failed(pool, job_id, err)
            drained.append({"job_id": job_id, "status": "failed", "error": err})
    return {"ok": True, "drained": len(drained), "jobs": drained}


@router.post("/compute_ic_annotations")
@router.get("/compute_ic_annotations")
async def cron_compute_ic_annotations(
    window_days: int = Query(30, ge=1, le=365),
) -> dict[str, Any]:
    """Traceability (principle 11): recompute IC change annotations after the
    daily IC refresh so the /evolution chart markers stay current without a
    manual trigger. Idempotent upsert; deterministic, no LLM."""
    from alpha_agent.evolution.metric_annotations import compute_ic_annotations

    pool = await get_pool(os.environ["DATABASE_URL"])
    started_at = datetime.now(UTC)
    try:
        written = await compute_ic_annotations(pool, window_days)
    except Exception as exc:  # noqa: BLE001 — surface in cron_runs, don't swallow
        err = f"{type(exc).__name__}: {exc}"
        await pool.execute(
            "INSERT INTO cron_runs (cron_name, started_at, finished_at, ok, error_count, details) "
            "VALUES ($1, $2, now(), false, 1, $3::jsonb)",
            "compute_ic_annotations",
            started_at,
            json.dumps({"error": err}),
        )
        raise
    await pool.execute(
        "INSERT INTO cron_runs (cron_name, started_at, finished_at, ok, error_count, details) "
        "VALUES ($1, $2, now(), true, 0, $3::jsonb)",
        "compute_ic_annotations",
        started_at,
        json.dumps({"written": written, "window_days": window_days}),
    )
    return {"ok": True, "written": written, "window_days": window_days}


# news_llm_enrich cron route removed 2026-05-17.
# The previous cron-side handler called get_settings() -> create_llm_client()
# which requires a global LLM key in the server env. That violates BYOK
# (the platform deliberately does not hold a global key; each user supplies
# their own). Read-time replacement: POST /api/news/enrich/{ticker} with
# Depends(get_llm_client), which sources the caller's stored BYOK key.
