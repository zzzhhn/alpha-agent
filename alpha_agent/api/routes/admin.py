"""POST /api/admin/refresh — user-triggered cron refresh via GitHub Actions.

Why this exists: cron-shards.yml is the canonical scheduler for fast_intraday
(every 2h during market) and slow_daily (daily 13:30 UTC). A user staring at
stale picks shouldn't wait for the next 2h tick. This route dispatches the
workflow on demand, with a rate-limit so the UI button can't burn Vercel quota.

Auth model: optional shared secret `REFRESH_SECRET` (set in Vercel env). When
unset, the route is open — acceptable for personal use, not for public deploy.

Failure shapes: every error returns 200 with `{ok: false, reason}` so the
frontend has a single response shape to decode. The only non-200 is 500 when
the request fails to even reach the GH API (network error).
"""
from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from alpha_agent.auth.dependencies import require_user

from alpha_agent.api.dependencies import get_db_pool

router = APIRouter(prefix="/api/admin", tags=["admin"])

# Cooldown window: minimum gap between consecutive refreshes for any one job.
# Tracks via cron_runs table (started_at column) rather than in-memory so the
# limit survives function instance recycling.
_COOLDOWN_MINUTES = 10
_GH_REPO = os.environ.get("GH_REPO", "zzzhhn/alpha-agent")
_GH_WORKFLOW = "cron-shards.yml"
_GH_REF = os.environ.get("GH_REF", "main")


class RefreshRequest(BaseModel):
    job: Literal["fast_intraday", "slow_daily", "both"] = "fast_intraday"


class RefreshResponse(BaseModel):
    ok: bool
    dispatched_at: str | None = None
    eta_minutes: int | None = None
    reason: str | None = None
    last_run_started_at: str | None = None


async def _cooldown_active(job: str) -> tuple[bool, datetime | None]:
    """True if `job` ran inside the cooldown window. Returns (active, last_started)."""
    pool = await get_db_pool()
    # `cron_runs.cron_name` is one of "slow_daily" / "fast_intraday" / "alert_dispatcher".
    # For job="both" check fast_intraday only (the one users primarily care about).
    probe = job if job != "both" else "fast_intraday"
    row = await pool.fetchrow(
        """
        SELECT started_at FROM cron_runs
        WHERE cron_name = $1
        ORDER BY started_at DESC
        LIMIT 1
        """,
        probe,
    )
    if row is None:
        return False, None
    last = row["started_at"]
    if last.tzinfo is None:
        last = last.replace(tzinfo=UTC)
    age = datetime.now(UTC) - last
    return age < timedelta(minutes=_COOLDOWN_MINUTES), last


@router.post("/refresh", response_model=RefreshResponse)
async def trigger_refresh(
    body: RefreshRequest,
    user_id: int = Depends(require_user),
) -> RefreshResponse:
    gh_token = os.environ.get("GH_PAT")
    if not gh_token:
        return RefreshResponse(
            ok=False,
            reason="GH_PAT env var not configured; cannot dispatch workflow",
        )

    active, last = await _cooldown_active(body.job)
    if active:
        return RefreshResponse(
            ok=False,
            reason=f"cooldown active ({_COOLDOWN_MINUTES}min); last run started recently",
            last_run_started_at=last.isoformat() if last else None,
        )

    # eta_minutes guides the UI banner. fast_intraday = ~18min wall;
    # slow_daily = ~17min; both = sequential ~35min.
    eta = {"fast_intraday": 18, "slow_daily": 17, "both": 35}[body.job]

    dispatch_url = (
        f"https://api.github.com/repos/{_GH_REPO}/actions/workflows/{_GH_WORKFLOW}/dispatches"
    )
    payload = {"ref": _GH_REF, "inputs": {"job": body.job}}
    headers = {
        "Authorization": f"Bearer {gh_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(dispatch_url, json=payload, headers=headers)
    if resp.status_code not in (204,):
        return RefreshResponse(
            ok=False,
            reason=f"GH API returned {resp.status_code}: {resp.text[:200]}",
            last_run_started_at=last.isoformat() if last else None,
        )

    return RefreshResponse(
        ok=True,
        dispatched_at=datetime.now(UTC).isoformat(),
        eta_minutes=eta,
        last_run_started_at=last.isoformat() if last else None,
    )


@router.get("/last_refresh")
async def last_refresh() -> dict:
    """Lightweight GET so the frontend can show 'last refreshed N min ago'
    without needing auth or write permission."""
    pool = await get_db_pool()
    rows = await pool.fetch(
        """
        SELECT cron_name, MAX(started_at) AS last
        FROM cron_runs
        WHERE cron_name IN ('fast_intraday', 'slow_daily')
        GROUP BY cron_name
        """
    )
    out: dict[str, str | None] = {"fast_intraday": None, "slow_daily": None}
    for r in rows:
        ts = r["last"]
        if ts is not None and ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        out[r["cron_name"]] = ts.isoformat() if ts else None
    return out
