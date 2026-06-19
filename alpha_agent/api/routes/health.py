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
    "rsrs",
    "analyst",
    "earnings",
    "news",
    "insider",
    "options",
    "premarket",
    "macro",
    "calendar",
    "political_impact",
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
    live_ic_30d: float | None = None
    live_ic_60d: float | None = None
    live_ic_90d: float | None = None
    weight_current: float | None = None
    tier: str = "unknown"
    # B1 (2026-05-19) joint diagnostics on the 30d window — surfaced in
    # AttributionTable next to live_ic_30d so the user sees not just the
    # latest IC but its stability (ICIR), annualized info ratio (IR), and
    # sample size (n_obs). All three derived on-the-fly from
    # signal_ic_history aggregation (no new table). Null when history
    # has fewer than 2 observations for the window.
    icir_30d: float | None = None
    ir_30d: float | None = None
    n_obs_30d: int = 0


class HealthSignalsResponse(BaseModel):
    signals: list[SignalStatus]


async def _compute_signal_metrics(
    pool, name: str, window_days: int,
) -> dict[str, Any]:
    """Pull recent IC observations for (signal, window) and derive joint
    diagnostics from the time series in one round-trip.

    Returns dict with keys:
      - ic_latest: most-recent IC value (None when no history)
      - icir: ic_mean / ic_std (annualization-agnostic ratio of mean to
        std-dev across observations; higher = more consistent)
      - ir: icir × √(252 / window_days), the annualized Information Ratio
      - n_obs: count of observations used (capped at 90, the LIMIT below)

    Both icir and ir are None when the time series has fewer than 2 valid
    observations or when the std is degenerate (constant IC). Caller
    (health_signals) attaches these to SignalStatus alongside the legacy
    live_ic_* fields without breaking the schema.
    """
    import math as _math

    import numpy as _np

    rows = await pool.fetch(
        "SELECT ic FROM signal_ic_history "
        "WHERE signal_name = $1 AND window_days = $2 AND horizon_days = 5 "
        "ORDER BY computed_at DESC LIMIT 90",
        name, window_days,
    )
    if not rows:
        return {"ic_latest": None, "icir": None, "ir": None, "n_obs": 0}
    ics = [float(r["ic"]) for r in rows if r["ic"] is not None]
    ic_latest = ics[0] if ics else None
    n_obs = len(ics)
    if n_obs < 2:
        return {"ic_latest": ic_latest, "icir": None, "ir": None, "n_obs": n_obs}
    arr = _np.asarray(ics, dtype=float)
    arr = arr[~_np.isnan(arr)]
    if arr.size < 2:
        return {"ic_latest": ic_latest, "icir": None, "ir": None, "n_obs": n_obs}
    mu = float(_np.mean(arr))
    sd = float(_np.std(arr, ddof=1))
    if sd <= 1e-9:
        return {"ic_latest": ic_latest, "icir": None, "ir": None, "n_obs": n_obs}
    icir = mu / sd
    ir = icir * _math.sqrt(252.0 / float(window_days))
    return {"ic_latest": ic_latest, "icir": icir, "ir": ir, "n_obs": n_obs}


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
    """Per-signal error summary + live IC, current weight, and tier color.

    Tier rule:
      red                = reason == 'auto_dropped_low_ic' OR weight_current == 0.0
      green              = min(ic_30d, ic_60d, ic_90d) > 0.02
      yellow             = 0.01 < min(ics) <= 0.02
      insufficient_data  = no IC history yet AND no weight row yet
                           (framework alive, IC backtest needs > 10 obs
                           per window which require ~30 trading days)
      unknown            = mixed state not matching above (catch-all)
    """
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

        # B1: pull last 90 IC observations for the 30d window in one
        # round-trip; derive latest IC + ICIR + IR + n_obs from the same
        # time series (saves 1 SQL call vs the legacy 3-fetchval shape).
        # 60d / 90d windows remain single-fetchval for backwards compat.
        metrics_30d = await _compute_signal_metrics(pool, name, 30)
        ic_30d = metrics_30d["ic_latest"]
        ic_60d_raw = await pool.fetchval(
            "SELECT ic FROM signal_ic_history "
            "WHERE signal_name = $1 AND window_days = 60 AND horizon_days = 5 "
            "ORDER BY computed_at DESC LIMIT 1",
            name,
        )
        ic_90d_raw = await pool.fetchval(
            "SELECT ic FROM signal_ic_history "
            "WHERE signal_name = $1 AND window_days = 90 AND horizon_days = 5 "
            "ORDER BY computed_at DESC LIMIT 1",
            name,
        )
        ic_60d = float(ic_60d_raw) if ic_60d_raw is not None else None
        ic_90d = float(ic_90d_raw) if ic_90d_raw is not None else None

        weight_row = await pool.fetchrow(
            "SELECT weight, reason FROM signal_weight_current "
            "WHERE signal_name = $1 AND status = 'live'",
            name,
        )
        weight_current = (
            float(weight_row["weight"]) if weight_row is not None else None
        )
        reason = weight_row["reason"] if weight_row is not None else None

        ics = [v for v in (ic_30d, ic_60d, ic_90d) if v is not None]
        # reason field carries the IC engine's intent verbatim. Order
        # matters: insufficient_data must be checked before the generic
        # weight==0 branch, otherwise the early-life "data accumulating"
        # state gets misclassified as the post-mortem "auto-dropped" red
        # tier and confuses users.
        if reason == "insufficient_data":
            tier = "insufficient_data"
        elif reason == "auto_dropped_low_ic" or (
            weight_current is not None and weight_current == 0.0
        ):
            tier = "red"
        elif ics and min(ics) > 0.02:
            tier = "green"
        elif ics and min(ics) > 0.01:
            tier = "yellow"
        elif not ics and weight_row is None:
            # No IC history AND no weight row: framework alive but
            # ic_backtest has never run for this signal. Same family as
            # the explicit insufficient_data above, surface identically.
            tier = "insufficient_data"
        else:
            tier = "unknown"

        out.append(
            SignalStatus(
                name=name,
                last_success=None,  # not yet tracked; M3 backlog
                last_error=(last_err["err_message"] if last_err else None),
                error_count_24h=count_24h,
                live_ic_30d=ic_30d,
                live_ic_60d=ic_60d,
                live_ic_90d=ic_90d,
                weight_current=weight_current,
                tier=tier,
                icir_30d=metrics_30d["icir"],
                ir_30d=metrics_30d["ir"],
                n_obs_30d=metrics_30d["n_obs"],
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


@router.get("/data_sources")
async def health_data_sources() -> dict[str, Any]:
    """Row count + last-write per ingest source, so the data page can show how
    much each source has actually pulled (not just that it's configured). FRED
    macro is fetched live per request (no stored table), hence null counts."""
    pool = await get_db_pool()

    async def _count(sql: str) -> dict[str, Any]:
        # Surface a per-source query failure in the payload rather than 500-ing
        # the whole endpoint or silently reporting 0 (anti-pattern guard).
        try:
            row = await pool.fetchrow(sql)
        except Exception as e:  # noqa: BLE001 — reported, not swallowed
            return {"rows": None, "last_fetched_at": None, "error": f"{type(e).__name__}: {e}"}
        return {
            "rows": int(row["n"]) if row and row["n"] is not None else 0,
            "last_fetched_at": row["ts"].isoformat() if row and row["ts"] else None,
        }

    return {
        "sources": {
            "finnhub": await _count(
                "SELECT count(*) AS n, max(computed_at) AS ts FROM earnings_finnhub"
            ),
            "edgar": await _count(
                "SELECT count(*) AS n, max(computed_at) AS ts FROM insider_form4"
            ),
            "news": await _count(
                "SELECT count(*) AS n, max(fetched_at) AS ts FROM news_items"
            ),
            "yfinance": await _count(
                "SELECT count(DISTINCT ticker) AS n, max(fetched_at) AS ts "
                "FROM daily_signals_fast"
            ),
            "fred": None,
        }
    }
