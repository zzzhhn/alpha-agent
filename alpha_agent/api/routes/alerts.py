"""GET /api/alerts/recent — list latest alert_queue rows.

alert_queue is populated by the fast_intraday cron whenever a ticker's
rating or composite crosses a notable threshold. M2 wrote the rows; M4b
exposes them for the frontend timeline. Spec §4.3.

Always returns 200; an empty list is "no alerts yet", not an error.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from jose import JWTError, jwt
from pydantic import BaseModel, Field, field_validator

from alpha_agent.alerts.triage import assess_alert
from alpha_agent.api.dependencies import get_db_pool
from alpha_agent.auth.dependencies import require_user
from alpha_agent.news.event_reaction import EventReaction
from alpha_agent.news.event_watch import read_event_evidence

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


class EventWatchItem(BaseModel):
    id: str
    ticker: str
    title: str
    source: str
    url: str
    published_at: datetime | None
    published_date: date | None
    published_at_quality: Literal['sec_accepted', 'source_timestamp', 'date_only', 'unavailable', 'unverified']
    first_seen_at: datetime
    kind: Literal['sec_filing', 'earnings', 'investor_release', 'management_change',
                  'guidance', 'merger_acquisition', 'regulatory', 'media_report']
    status: Literal['observed', 'corrected', 'withdrawn']
    evidence_class: Literal['official', 'media']
    reaction: EventReaction | None = None


class EventWatchSourceCoverage(BaseModel):
    ticker: str
    source: Literal['sec_edgar', 'investor_relations']
    status: Literal['healthy', 'stale', 'unavailable', 'not_checked', 'unsupported']
    last_attempt_at: datetime | None
    last_success_at: datetime | None


class EventWatchCoverage(BaseModel):
    status: Literal['healthy', 'stale', 'unavailable', 'not_checked', 'unsupported', 'partial']
    tracked_tickers: list[str]
    sources: list[EventWatchSourceCoverage]
    as_of: datetime


class EventWatchResponse(BaseModel):
    events: list[EventWatchItem]
    coverage: EventWatchCoverage


@router.get('/events', response_model=EventWatchResponse)
async def alerts_events(
    response: Response,
    ticker: str | None = Query(None, min_length=1, max_length=12, pattern=r'^[A-Za-z][A-Za-z0-9.-]{0,11}$'),
    limit: int = Query(20, ge=1, le=50),
    user_id: int = Depends(require_user),
) -> dict:
    """Return observed evidence separately from its source coverage."""
    response.headers['Cache-Control'] = 'private, no-store'
    return await read_event_evidence(await get_db_pool(), user_id, ticker.upper() if ticker else None, limit)


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
    occurrences: int = 1
    first_seen_at: str | None = None
    last_seen_at: str | None = None
    member_ids: list[int] = Field(default_factory=list)
    group_id: str | None = None
    group_token: str | None = None
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
    next_offset: int | None = None


class AlertStateRequest(BaseModel):
    status: Literal["open", "snoozed", "resolved"]
    snooze_until: datetime | None = None
    note: str | None = Field(default=None, max_length=500)


class AlertBatchStateRequest(AlertStateRequest):
    alert_ids: list[int] = Field(min_length=1, max_length=200)

    @field_validator("alert_ids")
    @classmethod
    def unique_alert_ids(cls, value: list[int]) -> list[int]:
        if len(set(value)) != len(value):
            raise ValueError("alert_ids must be unique")
        return value


class AlertBatchStateResponse(BaseModel):
    updated: int
    states: dict[int, AlertTriageState]


class AlertGroupStateRequest(AlertStateRequest):
    group_token: str = Field(min_length=1)


class AlertGroupUndoRequest(BaseModel):
    group_token: str = Field(min_length=1)
    undo_token: str = Field(min_length=1)


class AlertGroupStateResponse(BaseModel):
    updated: int
    state: AlertTriageState
    undo_token: str | None = None


class AlertAttentionResponse(BaseModel):
    """Compact private count for the sidebar badge.

    ``needs_action`` and ``critical`` use exactly the inbox's triage rules over
    the same bounded window, so the badge and the alerts page agree. It is the
    open work in that window, not a count of all historical alerts.
    """

    needs_action: int
    critical: int
    window: int
    newest_at: str | None
    as_of: str
    source_status: Literal["fresh", "stale", "empty"]


# Same first page of 50 groups the alerts workbench loads.
_ATTENTION_WINDOW = 50
# Inbox queue boundary: triage_score >= 45 is "needs action".
_NEEDS_ACTION_SCORE = 45
_NEW_YORK = ZoneInfo("America/New_York")


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
    response: Response,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0, le=2**63 - 1),
    user_id: int = Depends(require_user),
) -> AlertInboxResponse:
    """Return a page of newest groups, ranked for the user's decisions."""
    response.headers["Cache-Control"] = "private, no-store"
    return await _build_inbox(await get_db_pool(), user_id, limit, offset)


@router.get("/attention", response_model=AlertAttentionResponse)
async def alerts_attention(
    response: Response,
    user_id: int = Depends(require_user),
) -> AlertAttentionResponse:
    """Private pending-work count for the sidebar; never shared-cached."""
    pool = await get_db_pool()
    inbox = await _build_inbox(pool, user_id, _ATTENTION_WINDOW, sign_groups=False)
    open_items = [item for item in inbox.alerts if item.state.status == "open"]
    needs = [item for item in open_items if item.triage_score >= _NEEDS_ACTION_SCORE]
    newest = max((item.created_at for item in inbox.alerts), default=None)
    response.headers["Cache-Control"] = "private, max-age=60"
    return AlertAttentionResponse(
        needs_action=inbox.counts.needs_action,
        critical=sum(item.severity == "critical" for item in needs),
        window=len(inbox.alerts),
        newest_at=newest,
        as_of=inbox.as_of,
        source_status=inbox.source_status,
    )


def _alert_token_key() -> bytes:
    secret = os.environ.get("NEXTAUTH_SECRET")
    if not secret:
        raise HTTPException(status_code=503, detail="alert group signing unavailable")
    return hmac.digest(secret.encode(), b"alpha-agent:alert-group:v1", "sha256")


def _alert_token(user_id: int, kind: str, **claims: Any) -> str:
    return jwt.encode({"sub": str(user_id), "kind": kind, **claims}, _alert_token_key(), algorithm="HS256")


def _alert_claims(token: str, user_id: int, kind: str) -> dict:
    try:
        claims = jwt.decode(token, _alert_token_key(), algorithms=["HS256"])
    except JWTError as exc:
        raise HTTPException(status_code=422, detail="invalid alert group credential") from exc
    if claims.get("kind") != kind:
        raise HTTPException(status_code=422, detail="invalid alert group credential")
    if claims.get("sub") != str(user_id):
        raise HTTPException(status_code=403, detail="alert group credential belongs to another user")
    return claims


def _group_state(states: list[AlertTriageState]) -> AlertTriageState:
    # An older open occurrence still makes the group actionable.
    return next((state for state in states if state.status == "open"), states[0])


async def _build_inbox(
    pool: Any, user_id: int, limit: int, offset: int = 0, *, sign_groups: bool = True,
) -> AlertInboxResponse:
    # One statement observes both page selection and member expansion in the
    # same database snapshot. Rank only after fetching every member of the page.
    rows = await pool.fetch(
        """
        WITH page AS (
            SELECT upper(ticker) AS group_ticker, type,
                   (created_at AT TIME ZONE 'America/New_York')::date AS group_day,
                   max(created_at) AS latest, max(id) AS tie_breaker
            FROM alert_queue
            WHERE created_at IS NOT NULL
            GROUP BY group_ticker, type, group_day
            ORDER BY latest DESC, tie_breaker DESC
            LIMIT $1 OFFSET $2
        )
        SELECT a.id, a.ticker, a.type, a.payload, a.dedup_bucket, a.created_at,
               statement_timestamp() AS read_at
        FROM page p
        JOIN alert_queue a ON upper(a.ticker)=p.group_ticker AND a.type=p.type
            AND a.created_at >= (p.group_day::timestamp AT TIME ZONE 'America/New_York')
            AND a.created_at < ((p.group_day + 1)::timestamp AT TIME ZONE 'America/New_York')
        ORDER BY p.latest DESC, p.tie_breaker DESC, a.created_at DESC, a.id DESC
        """,
        limit + 1, offset,
    )
    now = (rows[0].get("read_at") if rows else None) or datetime.now(UTC)
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
    items: list[AlertInboxItem] = []
    for row in rows:
        ticker = str(row["ticker"]).upper()
        created_at = row["created_at"]
        if not isinstance(created_at, datetime):
            created_at = datetime.fromisoformat(str(created_at))
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        created_at = created_at.astimezone(UTC)
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

    groups: dict[tuple[str, str, date], list[AlertInboxItem]] = {}
    for item in items:
        ny_date = datetime.fromisoformat(item.created_at).astimezone(_NEW_YORK).date()
        groups.setdefault((item.ticker, item.type, ny_date), []).append(item)

    items = []
    for (ticker, alert_type, ny_date), members in list(groups.items())[:limit]:
        members.sort(key=lambda item: (item.created_at, item.id), reverse=True)
        representative = members[0]
        ids = [member.id for member in members]
        group_id = json.dumps([ticker, alert_type, ny_date.isoformat()], separators=(",", ":"))
        items.append(representative.model_copy(update={
            "occurrences": len(members),
            "first_seen_at": members[-1].created_at,
            "last_seen_at": representative.created_at,
            "member_ids": ids,
            "group_id": group_id,
            "group_token": _alert_token(
                user_id, "window", group_id=group_id, ids=ids, as_of=now.isoformat(),
            ) if sign_groups else None,
            "triage_score": max(member.triage_score for member in members),
            "state": _group_state([member.state for member in members]),
        }))

    items.sort(key=lambda item: (item.triage_score, item.created_at, item.id), reverse=True)
    open_items = [item for item in items if item.state.status == "open"]
    snoozed_items = [item for item in items if item.state.status == "snoozed"]
    counts = AlertInboxCounts(
        needs_action=sum(item.triage_score >= _NEEDS_ACTION_SCORE for item in open_items),
        watch=len(snoozed_items) + sum(
            25 <= item.triage_score < _NEEDS_ACTION_SCORE for item in open_items
        ),
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
        next_offset=offset + limit if len(groups) > limit else None,
    )


def _validated_snooze_until(body: AlertStateRequest, now: datetime) -> datetime | None:
    snooze_until = body.snooze_until
    if snooze_until is not None and snooze_until.tzinfo is None:
        snooze_until = snooze_until.replace(tzinfo=UTC)
    if body.status == "snoozed":
        if snooze_until is None or snooze_until <= now:
            raise HTTPException(status_code=422, detail="snooze_until must be in the future")
    return snooze_until


async def _upsert_alert_state(
    connection: Any,
    user_id: int,
    alert_id: int,
    body: AlertStateRequest,
    now: datetime,
    snooze_until: datetime | None,
) -> AlertTriageState:
    row = await connection.fetchrow(
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


@router.post("/state/batch", response_model=AlertBatchStateResponse)
async def set_alert_states_batch(
    body: AlertBatchStateRequest,
    user_id: int = Depends(require_user),
) -> AlertBatchStateResponse:
    """Atomically update 1–200 unique alerts for this user.

    Any missing alert returns 404 without writes. Revert a decision by calling
    again with status ``open`` (clears snooze_until and resolved_at).
    """
    now = datetime.now(UTC)
    snooze_until = _validated_snooze_until(body, now)
    pool = await get_db_pool()
    async with pool.acquire() as connection, connection.transaction():
        rows = await connection.fetch(
            "SELECT id FROM alert_queue WHERE id = ANY($1::bigint[]) ORDER BY id FOR KEY SHARE",
            body.alert_ids,
        )
        if len(rows) != len(body.alert_ids):
            raise HTTPException(status_code=404, detail="alert not found")
        states = {}
        for alert_id in body.alert_ids:
            states[alert_id] = await _upsert_alert_state(
                connection, user_id, alert_id, body, now, snooze_until,
            )
    return AlertBatchStateResponse(updated=len(states), states=states)


async def _lock_group_members(connection: Any, ids: list[int]) -> None:
    # Take the same row order as legacy batch writes. A group decision must
    # capture prior state and write atomically even for previously untouched rows.
    rows = await connection.fetch(
        "SELECT id FROM alert_queue WHERE id=ANY($1::bigint[]) ORDER BY id FOR UPDATE", ids,
    )
    if len(rows) != len(ids):
        raise HTTPException(status_code=404, detail="alert group member not found")


async def _stored_group_states(connection: Any, user_id: int, ids: list[int]) -> dict[int, Any]:
    rows = await connection.fetch(
        "SELECT alert_id,status,snooze_until,resolved_at,note,updated_at "
        "FROM alert_triage_state WHERE user_id=$1 AND alert_id=ANY($2::bigint[])",
        user_id, ids,
    )
    return {row["alert_id"]: row for row in rows}


def _effective_group_state(states: dict[int, Any], ids: list[int], now: datetime) -> AlertTriageState:
    views = []
    for alert_id in ids:
        row = states.get(alert_id)
        if row is None:
            views.append(AlertTriageState())
            continue
        status = row["status"]
        if status == "snoozed" and row["snooze_until"] is not None and row["snooze_until"] <= now:
            status = "open"
        views.append(AlertTriageState(
            status=status, snooze_until=_iso(row["snooze_until"]),
            resolved_at=_iso(row["resolved_at"]), note=row["note"], updated_at=_iso(row["updated_at"]),
        ))
    return _group_state(views)


@router.post("/state/group", response_model=AlertGroupStateResponse)
async def set_alert_group_state(
    body: AlertGroupStateRequest,
    user_id: int = Depends(require_user),
) -> AlertGroupStateResponse:
    """Update the exact user-scoped group membership observed at inbox read."""
    ids = _alert_claims(body.group_token, user_id, "window")["ids"]
    requested_at = datetime.now(UTC)
    snooze_until = _validated_snooze_until(body, requested_at) if body.status == "snoozed" else None
    pool = await get_db_pool()
    async with pool.acquire() as connection, connection.transaction():
        await _lock_group_members(connection, ids)
        prior = await _stored_group_states(connection, user_id, ids)
        applied_at = datetime.now(UTC)
        if snooze_until is not None and snooze_until <= applied_at:
            raise HTTPException(status_code=422, detail="snooze_until must be in the future")
        resolved_at = applied_at if body.status == "resolved" else None
        await connection.execute(
            """
            INSERT INTO alert_triage_state
                (user_id,alert_id,status,snooze_until,resolved_at,note,updated_at)
            SELECT $1,member,$3,$4,$5,$6,$7 FROM unnest($2::bigint[]) AS member
            ON CONFLICT (user_id,alert_id) DO UPDATE SET
                status=EXCLUDED.status,snooze_until=EXCLUDED.snooze_until,
                resolved_at=EXCLUDED.resolved_at,note=EXCLUDED.note,updated_at=EXCLUDED.updated_at
            """,
            user_id, ids, body.status, snooze_until, resolved_at, body.note, applied_at,
        )
        undo = _alert_token(
            user_id, "undo", window=hashlib.sha256(body.group_token.encode()).hexdigest(),
            applied_at=applied_at.isoformat(),
            prior=[
                {"alert_id": alert_id, "status": row["status"], "note": row["note"],
                 "snooze_until": _iso(row["snooze_until"]), "resolved_at": _iso(row["resolved_at"])}
                for alert_id, row in prior.items()
            ],
        )
    return AlertGroupStateResponse(
        updated=len(ids), undo_token=undo,
        state=AlertTriageState(
            status=body.status, snooze_until=_iso(snooze_until), resolved_at=_iso(resolved_at),
            note=body.note, updated_at=_iso(applied_at),
        ),
    )


@router.post("/state/group/undo", response_model=AlertGroupStateResponse)
async def undo_alert_group_state(
    body: AlertGroupUndoRequest,
    user_id: int = Depends(require_user),
) -> AlertGroupStateResponse:
    """Restore the prior per-member states if this decision is still current."""
    ids = _alert_claims(body.group_token, user_id, "window")["ids"]
    undo = _alert_claims(body.undo_token, user_id, "undo")
    if undo["window"] != hashlib.sha256(body.group_token.encode()).hexdigest():
        raise HTTPException(status_code=422, detail="undo credential does not match the original group window")
    applied_at = datetime.fromisoformat(undo["applied_at"])
    pool = await get_db_pool()
    async with pool.acquire() as connection, connection.transaction():
        await _lock_group_members(connection, ids)
        current = await _stored_group_states(connection, user_id, ids)
        if len(current) != len(ids) or any(row["updated_at"] != applied_at for row in current.values()):
            raise HTTPException(status_code=409, detail="alert group state changed after this decision")
        prior = undo["prior"]
        prior_ids = [row["alert_id"] for row in prior]
        await connection.execute(
            "DELETE FROM alert_triage_state WHERE user_id=$1 AND alert_id=ANY($2::bigint[]) "
            "AND alert_id<>ALL($3::bigint[])",
            user_id, ids, prior_ids,
        )
        if prior:
            await connection.execute(
                """
                UPDATE alert_triage_state state SET
                    status=prior.status,note=prior.note,snooze_until=prior.snooze_until,
                    resolved_at=prior.resolved_at,updated_at=clock_timestamp()
                FROM jsonb_to_recordset($2::jsonb) AS prior(
                    alert_id bigint,status text,note text,snooze_until timestamptz,resolved_at timestamptz
                )
                WHERE state.user_id=$1 AND state.alert_id=prior.alert_id
                """,
                user_id, json.dumps(prior),
            )
        restored = await _stored_group_states(connection, user_id, ids)
    return AlertGroupStateResponse(
        updated=len(ids), state=_effective_group_state(restored, ids, datetime.now(UTC)),
    )


@router.post("/{alert_id}/state", response_model=AlertTriageState)
async def set_alert_state(
    alert_id: int,
    body: AlertStateRequest,
    user_id: int = Depends(require_user),
) -> AlertTriageState:
    """Persist a reversible per-user triage decision; status open reverts it."""
    now = datetime.now(UTC)
    snooze_until = _validated_snooze_until(body, now)
    pool = await get_db_pool()
    async with pool.acquire() as connection, connection.transaction():
        if not await connection.fetchval("SELECT id FROM alert_queue WHERE id=$1 FOR KEY SHARE", alert_id):
            raise HTTPException(status_code=404, detail="alert not found")
        return await _upsert_alert_state(connection, user_id, alert_id, body, now, snooze_until)
