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

import asyncio
import math
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from alpha_agent.api.dependencies import get_db_pool
from alpha_agent.core.types import RouterHealth
from alpha_agent.signals.registry import all_signal_names as _all_signal_names

router = APIRouter(prefix="/api/_health", tags=["health"])

# Derived from the single signal registry (source of truth). Previously a
# hand-kept list that had drifted (missing geopolitical_impact + supply_chain);
# deriving it means monitoring now covers every live signal automatically.
_SIGNAL_NAMES = _all_signal_names()


class HealthResponse(BaseModel):
    tunnel: str
    db: str
    last_slow_cron: str | None
    last_fast_cron: str | None
    last_dispatcher: str | None
    # WHY the db is down, verbatim from the driver. A bare "down" sends you
    # digging; "exceeded the data transfer quota" names the fix. Null when ok.
    db_error: str | None = None


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
    rows = await pool.fetch(
        "SELECT ic FROM signal_ic_history "
        "WHERE signal_name = $1 AND window_days = $2 AND horizon_days = 5 "
        "ORDER BY computed_at DESC LIMIT 90",
        name, window_days,
    )
    return _metrics_from_rows(rows, window_days)


def _metrics_from_rows(rows, window_days: int) -> dict[str, Any]:
    from statistics import mean, stdev

    if not rows:
        return {"ic_latest": None, "icir": None, "ir": None, "n_obs": 0}
    ics = [float(r["ic"]) for r in rows
           if r["ic"] is not None and math.isfinite(float(r["ic"]))]
    ic_latest = ics[0] if ics else None
    n_obs = len(ics)
    if n_obs < 2:
        return {"ic_latest": ic_latest, "icir": None, "ir": None, "n_obs": n_obs}
    mu = mean(ics)
    sd = stdev(ics)
    if sd <= 1e-9:
        return {"ic_latest": ic_latest, "icir": None, "ir": None, "n_obs": n_obs}
    icir = mu / sd
    ir = icir * math.sqrt(252.0 / float(window_days))
    return {"ic_latest": ic_latest, "icir": icir, "ir": ir, "n_obs": n_obs}


@router.get("", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Liveness probe: DB ping + last cron run timestamps.

    A health probe must never be taken down by the outage it exists to report.
    This one was: it correctly caught the ping failure and set db="down", then
    threw that away one line later because the _last() cron lookups queried the
    same dead pool unguarded, so the whole response 500'd with a bare "Internal
    Server Error". That is how the 2026-07-24 Neon data-transfer-quota outage
    stayed anonymous for two days — every DB-touching workflow emailed a
    failure, and the endpoint built to explain it could only 500 too.

    So: pool creation AND every query are guarded, and the driver's own message
    is surfaced in db_error rather than swallowed.
    """
    db_status = "ok"
    db_error: str | None = None
    pool = None
    try:
        pool = await get_db_pool()
        await pool.fetchval("SELECT 1")
    except Exception as exc:  # noqa: BLE001 — a probe reports, never raises
        db_status = "down"
        db_error = f"{type(exc).__name__}: {exc}"[:300]

    async def _last(cron_name: str) -> str | None:
        if pool is None or db_status != "ok":
            return None
        try:
            row = await pool.fetchrow(
                "SELECT started_at FROM cron_runs WHERE cron_name = $1 "
                "ORDER BY started_at DESC LIMIT 1",
                cron_name,
            )
        except Exception:  # noqa: BLE001 — a stale timestamp must not 500 the probe
            return None
        return row["started_at"].isoformat() if row else None

    return HealthResponse(
        tunnel="ok",
        db=db_status,
        db_error=db_error,
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
    success_query = """
        WITH latest AS (
            SELECT DISTINCT ON (ticker) ticker, breakdown, fetched_at
            FROM (
                SELECT ticker, breakdown, fetched_at FROM daily_signals_fast
                UNION ALL
                SELECT ticker, breakdown, fetched_at FROM daily_signals_slow
            ) all_signals ORDER BY ticker, fetched_at DESC
        )
        SELECT item->>'signal' AS signal_name, MAX(fetched_at) AS last_success
        FROM latest
        CROSS JOIN LATERAL jsonb_array_elements(
            COALESCE(breakdown->'breakdown', '[]'::jsonb)
        ) AS item
        WHERE COALESCE(item->>'error', '') = '' AND item->>'z' IS NOT NULL
        GROUP BY item->>'signal'
        """
    # Four bounded queries instead of six serial lookups per signal (85 total).
    success_rows, error_rows, ic_rows, weight_rows = await asyncio.gather(
        pool.fetch(success_query),
        pool.fetch("""
            SELECT component, (array_agg(err_message ORDER BY ts DESC))[1] AS last_error,
                   count(*) FILTER (WHERE ts > now() - INTERVAL '24 hours') AS error_count
            FROM error_log WHERE component = ANY($1::text[]) GROUP BY component
        """, [f"signals.{name}" for name in _SIGNAL_NAMES]),
        pool.fetch("""
            SELECT names.name AS signal_name, windows.days AS window_days, h.ic
            FROM unnest($1::text[]) AS names(name)
            CROSS JOIN (VALUES (30), (60), (90)) AS windows(days)
            CROSS JOIN LATERAL (
                SELECT ic, computed_at FROM signal_ic_history
                WHERE signal_name = names.name AND window_days = windows.days
                  AND horizon_days = 5
                ORDER BY computed_at DESC
                LIMIT CASE WHEN windows.days = 30 THEN 90 ELSE 1 END
            ) h ORDER BY names.name, windows.days, h.computed_at DESC
        """, _SIGNAL_NAMES),
        pool.fetch("SELECT signal_name, weight, reason FROM signal_weight_current WHERE status='live'"),
    )
    last_success_by_signal = {
        row["signal_name"]: row["last_success"] for row in success_rows
    }
    errors = {row["component"]: row for row in error_rows}
    weights_by_signal = {row["signal_name"]: row for row in weight_rows}
    history: dict[tuple[str, int], list] = {}
    for row in ic_rows:
        history.setdefault((row["signal_name"], row["window_days"]), []).append(row)
    out: list[SignalStatus] = []
    for name in _SIGNAL_NAMES:
        comp = f"signals.{name}"
        last_err = errors.get(comp)
        count_24h = int(last_err["error_count"]) if last_err else 0
        metrics_30d = _metrics_from_rows(history.get((name, 30), []), 30)
        ic_30d = metrics_30d["ic_latest"]
        ic_60d = _metrics_from_rows(history.get((name, 60), []), 60)["ic_latest"]
        ic_90d = _metrics_from_rows(history.get((name, 90), []), 90)["ic_latest"]
        weight_row = weights_by_signal.get(name)
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
                last_success=(
                    last_success_by_signal[name].isoformat()
                    if last_success_by_signal.get(name)
                    else None
                ),
                last_error=(last_err["last_error"] if last_err else None),
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


_DAG_REQUIREMENTS = {
    # A full daily price pull is eight shards; the immutable recommendation
    # publish follows six full-signal shards. Counting the whole window avoids
    # declaring the DAG healthy merely because the final shard happened to pass.
    "daily_prices": {"cadence_hours": 30, "required_runs": 8},
    "fast_intraday": {"cadence_hours": 30, "required_runs": 6},
    "recommendation_publish": {"cadence_hours": 30, "required_runs": 1},
    "l2_cycle": {"cadence_hours": 48, "required_runs": 1},
    "paper_fill": {"cadence_hours": 48, "required_runs": 1},
    "ic_backtest_monthly": {"cadence_hours": 24 * 35, "required_runs": 1},
}


@router.get("/dag")
async def health_dag() -> dict[str, Any]:
    """Critical decision DAG, evaluated from durable DB evidence.

    One bounded query returns the latest successful or failed execution for
    each scheduled node plus the latest immutable recommendation publication.
    """
    pool = await get_db_pool()
    rows = await pool.fetch(
        """
        WITH requirements AS (
            SELECT * FROM unnest($1::text[], $2::int[], $3::int[])
                AS r(name, cadence_hours, required_runs)
        ), cron_window AS (
            SELECT r.name, MAX(cr.finished_at) AS observed_at,
                   COALESCE(
                       BOOL_AND(cr.ok) FILTER (
                           WHERE cr.started_at >= now()
                             - make_interval(hours => r.cadence_hours)
                             AND cr.finished_at IS NOT NULL
                       ), false
                   ) AS ok,
                   COALESCE(SUM(cr.error_count) FILTER (
                       WHERE cr.started_at >= now()
                         - make_interval(hours => r.cadence_hours)
                   ), 0) AS error_count,
                   COUNT(*) FILTER (
                       WHERE cr.started_at >= now()
                         - make_interval(hours => r.cadence_hours)
                         AND cr.finished_at IS NOT NULL
                   ) AS observed_runs,
                   r.required_runs
            FROM requirements r
            LEFT JOIN cron_runs cr ON cr.cron_name=r.name
            GROUP BY r.name, r.cadence_hours, r.required_runs
        ), latest_publish AS (
            SELECT 'recommendation_publish'::text AS name,
                   finished_at AS observed_at,
                   (status='complete') AS ok,
                   CASE WHEN status='complete' THEN 0 ELSE 1 END AS error_count,
                   1::bigint AS observed_runs, 1 AS required_runs
            FROM research_run
            ORDER BY finished_at DESC NULLS LAST, id DESC
            LIMIT 1
        )
        SELECT * FROM cron_window
        UNION ALL
        SELECT * FROM latest_publish
        """,
        [name for name in _DAG_REQUIREMENTS if name != "recommendation_publish"],
        [
            item["cadence_hours"]
            for name, item in _DAG_REQUIREMENTS.items()
            if name != "recommendation_publish"
        ],
        [
            item["required_runs"]
            for name, item in _DAG_REQUIREMENTS.items()
            if name != "recommendation_publish"
        ],
    )
    by_name = {row["name"]: row for row in rows}
    now = datetime.now(UTC)
    nodes: list[dict[str, Any]] = []
    for name, requirement in _DAG_REQUIREMENTS.items():
        cadence_hours = int(requirement["cadence_hours"])
        required_runs = int(requirement["required_runs"])
        row = by_name.get(name)
        observed_at = row["observed_at"] if row else None
        if observed_at is not None and observed_at.tzinfo is None:
            observed_at = observed_at.replace(tzinfo=UTC)
        age_hours = (
            (now - observed_at).total_seconds() / 3600.0
            if observed_at is not None
            else None
        )
        status = (
            "missing"
            if row is None or observed_at is None
            else "stale"
            if age_hours is not None and age_hours > cadence_hours
            else "failed"
            if not row["ok"]
            else "incomplete"
            if int(row["observed_runs"] or 0) < required_runs
            else "healthy"
        )
        nodes.append({
            "name": name,
            "status": status,
            "last_observed_at": observed_at.isoformat() if observed_at else None,
            "age_hours": round(age_hours, 2) if age_hours is not None else None,
            "expected_within_hours": cadence_hours,
            "error_count": int(row["error_count"] or 0) if row else None,
            "observed_runs": int(row["observed_runs"] or 0) if row else 0,
            "required_runs": required_runs,
        })
    return {
        "overall": (
            "healthy" if all(node["status"] == "healthy" for node in nodes)
            else "degraded"
        ),
        "nodes": nodes,
    }


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
