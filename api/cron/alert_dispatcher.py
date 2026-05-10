"""Vercel cron: drain alert_queue.

Trigger: every 5min.
Phase 1 implementation: marks alerts dispatched + logs structured payload.
Phase 2+ adds real push channels (Telegram/email/webhook).

Spec §4.1, §5.2. Always returns 200 with {ok, dispatched_count}; never
raises 5xx.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from typing import Any

from alpha_agent.storage.postgres import get_pool
from alpha_agent.storage.queries import list_pending_alerts, mark_alert_dispatched

logger = logging.getLogger(__name__)


async def _push_to_channel(alert: dict[str, Any]) -> None:
    """Phase 1 stub: log structured JSON to stdout. Phase 2 adds real push."""
    payload = alert["payload"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    logger.info(
        "ALERT %s",
        json.dumps(
            {
                "ticker": alert["ticker"],
                "type": alert["type"],
                "payload": payload,
                "created_at": alert["created_at"].isoformat(),
            }
        ),
    )


async def handler() -> dict[str, Any]:
    """Vercel function entry point. Always returns a dict (never raises)."""
    pool = await get_pool(os.environ["DATABASE_URL"])
    now = datetime.now(UTC)

    pending = await list_pending_alerts(pool, limit=200)
    dispatched_count = 0
    for alert in pending:
        try:
            await _push_to_channel(dict(alert))
            await mark_alert_dispatched(pool, alert["id"])
            dispatched_count += 1
        except Exception as e:  # noqa: BLE001 — push failure must not abort the drain
            logger.error(
                "dispatcher: failed to push alert %d: %s: %s",
                alert["id"],
                type(e).__name__,
                e,
            )

    await pool.execute(
        "INSERT INTO cron_runs "
        "(cron_name, started_at, finished_at, ok, error_count, details) "
        "VALUES ($1, $2, $3, $4, $5, $6::jsonb)",
        "alert_dispatcher",
        now,
        datetime.now(UTC),
        True,
        0,
        json.dumps({"dispatched_count": dispatched_count}),
    )
    return {"ok": True, "dispatched_count": dispatched_count}
