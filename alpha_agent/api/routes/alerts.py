"""GET /api/alerts/recent — list latest alert_queue rows.

alert_queue is populated by the fast_intraday cron whenever a ticker's
rating or composite crosses a notable threshold. M2 wrote the rows; M4b
exposes them for the frontend timeline. Spec §4.3.

Always returns 200; an empty list is "no alerts yet", not an error.
"""
from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Query
from pydantic import BaseModel

from alpha_agent.api.dependencies import get_db_pool

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
