"""Vercel-clocked dispatch of long GitHub workflows (allowlist only)."""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime

import httpx
from fastapi import HTTPException

from alpha_agent.data.capacity import read_capacity

REPO = os.environ.get("GH_REPO", "zzzhhn/alpha-agent")
REF = os.environ.get("GH_REF", "main")
# Inputs replicate what the former `schedule:` runs used. BRAIN self-corr
# backfill keeps its low scheduled limit (about 45 rapid requests locked the
# endpoint on 2026-07-13); a manual dispatch defaults to 120.
WORKFLOWS: dict[str, dict[str, str]] = {
    "earnings-finnhub": {},
    "insider-form4": {},
    "brain-mining-loop": {},
    "brain-backfill-selfcorr": {"limit": "30"},
}


async def dispatch_workflow(pool, workflow: str, *, now: datetime | None = None,
                            post=None) -> dict:
    if workflow not in WORKFLOWS:
        raise HTTPException(404, "unknown workflow")
    now = now or datetime.now(UTC)
    day = now.date().isoformat()
    name = f"dispatch_{workflow}"
    seen = await pool.fetchval(
        "SELECT 1 FROM cron_runs WHERE cron_name=$1 AND started_at >= $2 "
        "AND details->>'day'=$3 LIMIT 1",
        name, datetime.combine(now.date(), datetime.min.time(), UTC), day,
    )
    if seen:
        return {"ok": True, "workflow": workflow, "skipped": "already_dispatched_today"}
    details: dict = {"day": day, "workflow": workflow}
    capacity = await read_capacity(pool)
    if not capacity["allow_writes"]:
        details.update(status="paused", reason=capacity["reason"])
    else:
        token = (os.environ.get("GH_PAT") or "").strip()
        if not token:
            details.update(status="failed", reason="gh_pat_missing")
        else:
            payload = {"ref": REF}
            if WORKFLOWS[workflow]:
                payload["inputs"] = WORKFLOWS[workflow]
            try:
                if post is None:
                    async with httpx.AsyncClient(timeout=15) as client:
                        response = await client.post(
                            f"https://api.github.com/repos/{REPO}/actions/workflows/{workflow}.yml/dispatches",
                            headers={"Authorization": f"Bearer {token}",
                                     "Accept": "application/vnd.github+json",
                                     "X-GitHub-Api-Version": "2022-11-28"},
                            json=payload)
                    status = response.status_code
                else:
                    status = await post(workflow, payload)
            except httpx.HTTPError as exc:
                status = None
                details["error_type"] = type(exc).__name__
            details.update(status="dispatched" if status == 204 else "failed",
                           http_status=status)
    ok = details["status"] in ("dispatched", "paused")
    await pool.execute(
        "INSERT INTO cron_runs (cron_name, started_at, finished_at, ok, error_count, details) "
        "VALUES ($1, $2, now(), $3, $4, $5::jsonb)",
        name, now, ok, 0 if ok else 1, json.dumps(details),
    )
    return {"ok": ok, **details}
