"""Sidebar navigation status: one bounded public read plus one private count.

``GET /api/nav/status`` aggregates the global, non-personal states the sidebar
needs (recommendation freshness and the factor-evolution loop) in a single
request, so the sidebar never polls one endpoint per item. Responses are edge
cached. ``GET /api/alerts/attention`` (alerts router) stays authenticated and
private because pending alert work depends on the user's positions.
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import APIRouter, Response

from alpha_agent.api.cache_headers import set_public_cache
from alpha_agent.api.dependencies import get_db_pool
from alpha_agent.api.nav_status import classify_evolution, classify_picks
from alpha_agent.market_session import (
    latest_completed_xnys_session,
    next_xnys_session,
    xnys_sessions,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/nav", tags=["nav"])

_GH_REPO = os.environ.get("GH_REPO", "zzzhhn/alpha-agent")
_FACTOR_LOOP_WORKFLOW = "daily-factor-loop.yml"
# Workflow enablement changes rarely; one GitHub read per warm instance per
# window keeps the sidebar far away from the authenticated rate limit.
_WORKFLOW_TTL_S = 900.0
_workflow_cache: dict[str, Any] = {"ts": None, "state": None}


async def _factor_loop_workflow_state() -> str | None:
    """GitHub Actions state of the daily factor loop, or None when unreadable."""
    now = time.monotonic()
    cached_at = _workflow_cache["ts"]
    if cached_at is not None and now - cached_at < _WORKFLOW_TTL_S:
        return _workflow_cache["state"]
    token = (os.environ.get("GH_PAT") or "").strip()
    if not token:
        state = None
    else:
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                resp = await client.get(
                    f"https://api.github.com/repos/{_GH_REPO}/actions/workflows/{_FACTOR_LOOP_WORKFLOW}",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2022-11-28",
                    },
                )
            if resp.status_code == 404:
                state = "not_found"
            elif resp.status_code == 200:
                value = resp.json().get("state")
                state = value if isinstance(value, str) else None
            else:
                state = None
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("factor loop workflow state unavailable: %s", type(exc).__name__)
            state = None
    # Cache failures too: a GitHub outage must not turn every sidebar read
    # into another outbound call. The response reports "unknown" meanwhile.
    _workflow_cache.update(ts=now, state=state)
    return state


def _details(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return decoded if isinstance(decoded, dict) else {}
    return {}


@router.get("/status")
async def nav_status(response: Response) -> dict[str, Any]:
    """Global sidebar status in one round trip of four indexed reads."""
    pool = await get_db_pool()
    now = datetime.now(UTC)
    expected = latest_completed_xnys_session(now)
    # One statement keeps this to a single DB round trip on the slow
    # cross-region link. Every sub-select is LIMIT 1 on an indexed path.
    row = await pool.fetchrow(
        """
        SELECT
          (SELECT jsonb_build_object('market_date', scheduled_for_date,
                                     'passed', health_json->'passed')
             FROM research_run
            WHERE run_type = 'daily_close' AND status = 'complete'
            ORDER BY scheduled_for_date DESC, finished_at DESC NULLS LAST, id DESC
            LIMIT 1) AS latest_run,
          (SELECT jsonb_build_object('started_at', started_at, 'ok', ok,
                                     'details', details)
             FROM cron_runs WHERE cron_name = 'recommendation_publish'
            ORDER BY started_at DESC LIMIT 1) AS last_publish,
          (SELECT jsonb_build_object('started_at', started_at,
                                     'finished_at', finished_at, 'ok', ok)
             FROM cron_runs WHERE cron_name = 'daily_factor_loop'
            ORDER BY started_at DESC LIMIT 1) AS factor_loop,
          (SELECT count(*) FROM config_change_log WHERE status = 'pending')
            AS pending_policy,
          (SELECT count(*) FROM factor_proposals WHERE status = 'pending')
            AS pending_factor
        """
    )
    latest = _details(row["latest_run"]) if row else {}
    latest_date = (
        datetime.fromisoformat(latest["market_date"]).date()
        if latest.get("market_date") else None
    )
    sessions_behind = (
        len([day for day in xnys_sessions(latest_date, expected) if day > latest_date])
        if latest_date is not None and latest_date < expected else 0
    )
    publish_raw = _details(row["last_publish"]) if row else {}
    publish_details = _details(publish_raw.get("details"))
    last_publish = (
        {
            "started_at": datetime.fromisoformat(publish_raw["started_at"]),
            "ok": publish_raw.get("ok"),
            "reason": publish_details.get("reason") or publish_details.get("publish_status"),
        }
        if publish_raw.get("started_at") else None
    )
    picks = classify_picks(
        latest_market_date=latest_date,
        latest_health_passed=latest.get("passed") if isinstance(latest.get("passed"), bool) else None,
        expected_session=expected,
        sessions_behind=sessions_behind,
        next_session=next_xnys_session(expected),
        last_publish=last_publish,
        now=now,
    )

    loop_raw = _details(row["factor_loop"]) if row else {}
    last_run = (
        {
            "started_at": datetime.fromisoformat(loop_raw["started_at"]),
            "finished_at": (
                datetime.fromisoformat(loop_raw["finished_at"])
                if loop_raw.get("finished_at") else None
            ),
            "ok": loop_raw.get("ok"),
        }
        if loop_raw.get("started_at") else None
    )
    pending = (
        int(row["pending_policy"] or 0) + int(row["pending_factor"] or 0)
        if row else None
    )
    evolution = classify_evolution(
        workflow_state=await _factor_loop_workflow_state(),
        last_run=last_run,
        pending_reviews=pending,
        now=now,
    )
    set_public_cache(response, s_maxage=120, swr=600)
    return {"as_of": now.isoformat(), "picks": picks, "evolution": evolution}
