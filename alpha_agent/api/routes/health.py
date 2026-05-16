"""Health endpoints — deployment ground truth for CLAUDE.md 三板斧.

Four independent endpoints:
  GET /api/_health         — DB ping + last cron timestamps
  GET /api/_health/signals — per-signal error counts from error_log
  GET /api/_health/cron    — last 5 runs per cron name
  GET /api/_health/routers — which routers loaded vs which silently failed

All routes are decoupled from business routes so a broken picks/stock/brief
does not prevent health-check from answering.  Spec §5.7.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from alpha_agent.api.dependencies import get_db_pool
from alpha_agent.core.types import RouterHealth

router = APIRouter(prefix="/api/_health", tags=["health"])

_SIGNAL_NAMES = [
    "factor",
    "technicals",
    "analyst",
    "earnings",
    "news",
    "insider",
    "options",
    "premarket",
    "macro",
    "calendar",
]


class HealthResponse(BaseModel):
    tunnel: str
    db: str
    last_slow_cron: str | None
    last_fast_cron: str | None
    last_dispatcher: str | None


class SignalStatus(BaseModel):
    name: str
    last_success: str | None
    last_error: str | None
    error_count_24h: int


class HealthSignalsResponse(BaseModel):
    signals: list[SignalStatus]


@router.get("", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Liveness probe: DB ping + last cron run timestamps."""
    pool = await get_db_pool()
    try:
        await pool.fetchval("SELECT 1")
        db_status = "ok"
    except Exception:  # noqa: BLE001 — surface as field, not 500
        db_status = "down"

    async def _last(cron_name: str) -> str | None:
        row = await pool.fetchrow(
            "SELECT started_at FROM cron_runs WHERE cron_name = $1 "
            "ORDER BY started_at DESC LIMIT 1",
            cron_name,
        )
        return row["started_at"].isoformat() if row else None

    return HealthResponse(
        tunnel="ok",
        db=db_status,
        last_slow_cron=await _last("slow_daily"),
        last_fast_cron=await _last("fast_intraday"),
        last_dispatcher=await _last("alert_dispatcher"),
    )


@router.get("/signals", response_model=HealthSignalsResponse)
async def health_signals() -> HealthSignalsResponse:
    """Per-signal error summary from the last 24 hours."""
    pool = await get_db_pool()
    out: list[SignalStatus] = []
    for name in _SIGNAL_NAMES:
        comp = f"signals.{name}"
        last_err = await pool.fetchrow(
            "SELECT ts, err_message FROM error_log "
            "WHERE component = $1 ORDER BY ts DESC LIMIT 1",
            comp,
        )
        count_24h: int = await pool.fetchval(
            "SELECT COUNT(*) FROM error_log "
            "WHERE component = $1 AND ts > now() - INTERVAL '24 hours'",
            comp,
        ) or 0
        out.append(
            SignalStatus(
                name=name,
                last_success=None,  # not yet tracked; M3 backlog
                last_error=(last_err["err_message"] if last_err else None),
                error_count_24h=count_24h,
            )
        )
    return HealthSignalsResponse(signals=out)


@router.get("/cron")
async def health_cron() -> dict[str, Any]:
    """Last 5 cron runs per cron name."""
    pool = await get_db_pool()
    out: dict[str, list[dict[str, Any]]] = {}
    for name in ("slow_daily", "fast_intraday", "alert_dispatcher"):
        rows = await pool.fetch(
            "SELECT started_at, finished_at, ok, error_count, details "
            "FROM cron_runs WHERE cron_name = $1 ORDER BY started_at DESC LIMIT 5",
            name,
        )
        out[name] = [
            {
                "started_at": r["started_at"].isoformat(),
                "finished_at": r["finished_at"].isoformat() if r["finished_at"] else None,
                "ok": r["ok"],
                "error_count": r["error_count"],
            }
            for r in rows
        ]
    return {"cron": out}


@router.get("/routers")
async def health_routers(request: Request) -> dict[str, Any]:
    """Structured manifest of router cold-start outcomes.

    Reads app.state.router_health (populated by the _load helper in both
    entry points). Use this to detect a silently-missing route: per-block
    try/except hides ImportError as a 404 forever, so the deploy goes
    READY but the route never serves. Without this endpoint that failure
    is invisible from curl. Returns {total, loaded, failed, routers[]}.
    """
    health: list[RouterHealth] = getattr(request.app.state, "router_health", [])
    return {
        "total": len(health),
        "loaded": sum(1 for r in health if r.loaded),
        "failed": sum(1 for r in health if not r.loaded),
        "routers": [
            {"name": r.name, "loaded": r.loaded, "error": r.error}
            for r in health
        ],
    }


_KNOWN_NEWS_SOURCES = (
    "finnhub", "fmp", "rss_yahoo",
    "truth_social", "fed_rss", "ofac_rss",
)


@router.get("/news_freshness")
async def health_news_freshness() -> dict[str, Any]:
    """Per-source last_fetched_at + 24h item count + LLM backlog.

    Lets you tell at a glance whether one adapter has gone dark.
    """
    pool = await get_db_pool()
    rows = await pool.fetch(
        """
        WITH all_tables AS (
            SELECT source, fetched_at FROM news_items
            UNION ALL
            SELECT source, fetched_at FROM macro_events
        )
        SELECT source,
               MAX(fetched_at) AS last_fetched_at,
               COUNT(*) FILTER (WHERE fetched_at > now() - interval '24 hours')
                   AS items_24h
        FROM all_tables
        WHERE source = ANY($1)
        GROUP BY source
        """,
        list(_KNOWN_NEWS_SOURCES),
    )
    by_source = {r["source"]: r for r in rows}
    sources = []
    for name in _KNOWN_NEWS_SOURCES:
        r = by_source.get(name)
        sources.append({
            "name": name,
            "last_fetched_at": r["last_fetched_at"].isoformat() if r and r["last_fetched_at"] else None,
            "items_24h": int(r["items_24h"]) if r else 0,
        })
    llm_backlog = await pool.fetchval(
        "SELECT (SELECT count(*) FROM news_items WHERE llm_processed_at IS NULL) + "
        "(SELECT count(*) FROM macro_events WHERE llm_processed_at IS NULL)"
    )
    return {"sources": sources, "llm_backlog": int(llm_backlog or 0)}
