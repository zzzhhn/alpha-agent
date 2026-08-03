"""GET /api/alerts/recent — list latest alert_queue rows.

alert_queue is populated by the fast_intraday cron whenever a ticker's
rating or composite crosses a notable threshold. M2 wrote the rows; M4b
exposes them for the frontend timeline. Spec §4.3.

Always returns 200; an empty list is "no alerts yet", not an error.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from alpha_agent.alerts.triage import assess_alert
from alpha_agent.api.dependencies import get_db_pool
from alpha_agent.auth.dependencies import require_user

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


class Alert(BaseModel):
    id: int
    ticker: str
    type: str
    payload: dict | list | None
    dedup_bucket: int
    created_at: str


class AlertsResponse(BaseModel):
    alerts: list[Alert]


class AlertContext(BaseModel):
    in_position: bool
    in_recommendation: bool
    in_watchlist: bool
    recommendation_rank: int | None = None
    recommendation_run_id: int | None = None
    recommendation_market_date: str | None = None


class AlertTriageState(BaseModel):
    status: Literal["open", "snoozed", "resolved"] = "open"
    snooze_until: str | None = None
    resolved_at: str | None = None
    note: str | None = None
    updated_at: str | None = None


class AlertInboxItem(Alert):
    severity: Literal["critical", "warning", "info"]
    relevance: Literal["position", "recommendation", "market", "watchlist", "record"]
    triage_score: int
    freshness_score: int
    confidence_score: int
    confidence: Literal["high", "medium", "low"]
    source_count: int
    stale: bool
    context: AlertContext
    state: AlertTriageState


class AlertInboxCounts(BaseModel):
    needs_action: int
    watch: int
    record: int
    resolved: int


class AlertInboxResponse(BaseModel):
    alerts: list[AlertInboxItem]
    counts: AlertInboxCounts
    as_of: str
    source_status: Literal["fresh", "stale", "empty"]


class AlertStateRequest(BaseModel):
    status: Literal["open", "snoozed", "resolved"]
    snooze_until: datetime | None = None
    note: str | None = Field(default=None, max_length=500)


def _parse_payload(raw):
    """asyncpg JSONB columns come back as already-decoded dict/list when
    the column registration includes JSON codec, but defensively handle
    str (when codec not registered) too."""
    if raw is None:
        return None
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None
    return raw


@router.get("/recent", response_model=AlertsResponse)
async def alerts_recent(
    ticker: str | None = Query(None, min_length=1, max_length=10),
    limit: int = Query(20, ge=1, le=100),
) -> AlertsResponse:
    """Latest `limit` alerts, newest first. `ticker` optionally narrows
    to a single symbol (uppercased server-side)."""
    pool = await get_db_pool()
    if ticker:
        sql = (
            "SELECT id, ticker, type, payload, dedup_bucket, created_at "
            "FROM alert_queue WHERE ticker = $1 "
            "ORDER BY created_at DESC LIMIT $2"
        )
        rows = await pool.fetch(sql, ticker.upper(), limit)
    else:
        sql = (
            "SELECT id, ticker, type, payload, dedup_bucket, created_at "
            "FROM alert_queue "
            "ORDER BY created_at DESC LIMIT $1"
        )
        rows = await pool.fetch(sql, limit)
    alerts = [
        Alert(
            id=r["id"],
            ticker=r["ticker"],
            type=r["type"],
            payload=_parse_payload(r["payload"]),
            dedup_bucket=r["dedup_bucket"],
            created_at=r["created_at"].isoformat()
            if isinstance(r["created_at"], datetime) else str(r["created_at"]),
        )
        for r in rows
    ]
    return AlertsResponse(alerts=alerts)


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    return value.isoformat() if isinstance(value, datetime) else str(value)


async def _decision_context(pool: Any, user_id: int) -> tuple[
    set[str], set[str], dict[str, tuple[int | None, int | None, str | None]]
]:
    """Load the three small ticker sets used by deterministic triage.

    These queries are intentionally bounded to current user state and the
    latest canonical recommendation run. They do not scan historical market
    data or duplicate any payload into alert_queue.
    """
    position_rows = await pool.fetch(
        """
        SELECT sp.ticker
        FROM sim_position sp
        JOIN sim_account sa ON sa.id = sp.account_id
        WHERE sa.user_id = $1 AND sp.cohort_id = sa.reset_count AND sp.qty > 0
        """,
        user_id,
    )
    watchlist_rows = await pool.fetch(
        "SELECT ticker FROM user_watchlist WHERE user_id = $1",
        user_id,
    )
    recommendation_rows = await pool.fetch(
        """
        WITH latest AS (
            SELECT id, scheduled_for_date
            FROM research_run
            WHERE run_type = 'daily_close' AND status = 'complete'
            ORDER BY scheduled_for_date DESC, finished_at DESC NULLS LAST, id DESC
            LIMIT 1
        )
        SELECT rs.ticker, rs.rank, latest.id AS run_id,
               latest.scheduled_for_date AS market_date
        FROM rating_snapshot rs
        JOIN latest ON latest.id = rs.run_id
        WHERE rs.eligible = true AND rs.rank IS NOT NULL AND rs.rank <= 50
        """
    )
    positions = {str(row["ticker"]).upper() for row in position_rows}
    watchlist = {str(row["ticker"]).upper() for row in watchlist_rows}
    recommendations = {
        str(row["ticker"]).upper(): (
            int(row["rank"]) if row["rank"] is not None else None,
            int(row["run_id"]) if row["run_id"] is not None else None,
            str(row["market_date"]) if row["market_date"] is not None else None,
        )
        for row in recommendation_rows
    }
    return positions, watchlist, recommendations


@router.get("/inbox", response_model=AlertInboxResponse)
async def alerts_inbox(
    limit: int = Query(50, ge=1, le=100),
    user_id: int = Depends(require_user),
) -> AlertInboxResponse:
    """Decision-ranked alert inbox for the authenticated user."""
    pool = await get_db_pool()
    rows = await pool.fetch(
        """
        SELECT id, ticker, type, payload, dedup_bucket, created_at
        FROM alert_queue
        ORDER BY created_at DESC
        LIMIT $1
        """,
        limit,
    )
    positions, watchlist, recommendations = await _decision_context(pool, user_id)
    alert_ids = [int(row["id"]) for row in rows]
    state_rows = (
        await pool.fetch(
            """
            SELECT alert_id,
                   CASE
                     WHEN status = 'snoozed' AND snooze_until <= now() THEN 'open'
                     ELSE status
                   END AS status,
                   snooze_until, resolved_at, note, updated_at
            FROM alert_triage_state
            WHERE user_id = $1 AND alert_id = ANY($2::bigint[])
            """,
            user_id,
            alert_ids,
        )
        if alert_ids
        else []
    )
    states = {int(row["alert_id"]): row for row in state_rows}
    now = datetime.now(UTC)
    items: list[AlertInboxItem] = []
    for row in rows:
        ticker = str(row["ticker"]).upper()
        created_at = row["created_at"]
        if not isinstance(created_at, datetime):
            created_at = datetime.fromisoformat(str(created_at))
        payload = _parse_payload(row["payload"])
        payload_dict = payload if isinstance(payload, dict) else {}
        recommendation = recommendations.get(ticker)
        assessment = assess_alert(
            alert_type=str(row["type"]),
            payload=payload_dict,
            ticker=ticker,
            created_at=created_at,
            in_position=ticker in positions,
            in_recommendation=recommendation is not None,
            in_watchlist=ticker in watchlist,
            now=now,
        )
        state_row = states.get(int(row["id"]))
        items.append(AlertInboxItem(
            id=int(row["id"]),
            ticker=ticker,
            type=str(row["type"]),
            payload=payload,
            dedup_bucket=int(row["dedup_bucket"]),
            created_at=created_at.isoformat(),
            **assessment,
            context=AlertContext(
                in_position=ticker in positions,
                in_recommendation=recommendation is not None,
                in_watchlist=ticker in watchlist,
                recommendation_rank=recommendation[0] if recommendation else None,
                recommendation_run_id=recommendation[1] if recommendation else None,
                recommendation_market_date=recommendation[2] if recommendation else None,
            ),
            state=AlertTriageState(
                status=str(state_row["status"]) if state_row else "open",
                snooze_until=_iso(state_row["snooze_until"]) if state_row else None,
                resolved_at=_iso(state_row["resolved_at"]) if state_row else None,
                note=state_row["note"] if state_row else None,
                updated_at=_iso(state_row["updated_at"]) if state_row else None,
            ),
        ))

    items.sort(key=lambda item: (item.triage_score, item.created_at), reverse=True)
    open_items = [item for item in items if item.state.status == "open"]
    snoozed_items = [item for item in items if item.state.status == "snoozed"]
    counts = AlertInboxCounts(
        needs_action=sum(item.triage_score >= 45 for item in open_items),
        watch=len(snoozed_items) + sum(25 <= item.triage_score < 45 for item in open_items),
        record=sum(item.triage_score < 25 for item in open_items),
        resolved=sum(item.state.status == "resolved" for item in items),
    )
    newest = max((datetime.fromisoformat(item.created_at) for item in items), default=None)
    source_status: Literal["fresh", "stale", "empty"]
    if newest is None:
        source_status = "empty"
    elif now - newest > timedelta(hours=24):
        source_status = "stale"
    else:
        source_status = "fresh"
    return AlertInboxResponse(
        alerts=items,
        counts=counts,
        as_of=now.isoformat(),
        source_status=source_status,
    )


@router.post("/{alert_id}/state", response_model=AlertTriageState)
async def set_alert_state(
    alert_id: int,
    body: AlertStateRequest,
    user_id: int = Depends(require_user),
) -> AlertTriageState:
    """Persist a reversible per-user triage decision."""
    now = datetime.now(UTC)
    snooze_until = body.snooze_until
    if snooze_until is not None and snooze_until.tzinfo is None:
        snooze_until = snooze_until.replace(tzinfo=UTC)
    if body.status == "snoozed":
        if snooze_until is None or snooze_until <= now:
            raise HTTPException(status_code=422, detail="snooze_until must be in the future")
    pool = await get_db_pool()
    if not await pool.fetchval("SELECT EXISTS(SELECT 1 FROM alert_queue WHERE id=$1)", alert_id):
        raise HTTPException(status_code=404, detail="alert not found")
    row = await pool.fetchrow(
        """
        INSERT INTO alert_triage_state
            (user_id, alert_id, status, snooze_until, resolved_at, note, updated_at)
        VALUES ($1, $2, $3, $4, $5, $6, now())
        ON CONFLICT (user_id, alert_id) DO UPDATE SET
            status = EXCLUDED.status,
            snooze_until = EXCLUDED.snooze_until,
            resolved_at = EXCLUDED.resolved_at,
            note = EXCLUDED.note,
            updated_at = now()
        RETURNING status, snooze_until, resolved_at, note, updated_at
        """,
        user_id,
        alert_id,
        body.status,
        snooze_until if body.status == "snoozed" else None,
        now if body.status == "resolved" else None,
        body.note,
    )
    return AlertTriageState(
        status=row["status"],
        snooze_until=_iso(row["snooze_until"]),
        resolved_at=_iso(row["resolved_at"]),
        note=row["note"],
        updated_at=_iso(row["updated_at"]),
    )
