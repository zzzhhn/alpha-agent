"""Health endpoints — deployment ground truth for CLAUDE.md 三板斧.

Three independent endpoints:
  GET /api/_health        — DB ping + last cron timestamps
  GET /api/_health/signals — per-signal error counts from error_log
  GET /api/_health/cron   — last 5 runs per cron name

All routes are decoupled from business routes so a broken picks/stock/brief
does not prevent health-check from answering.  Spec §5.7.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from alpha_agent.api.dependencies import get_db_pool

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
