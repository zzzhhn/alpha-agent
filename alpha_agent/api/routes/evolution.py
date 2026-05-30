"""Evolution self-analysis endpoints.

Surfaces data produced by the self-loop (Phases 1a/1b/1c) for the /evolution
dashboard, and exposes human-gated mutations (approve/reject/rollback) for
methodology proposals written by the proposer (Phase 2a/2b).
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from alpha_agent.api.dependencies import get_db_pool
from alpha_agent.auth.dependencies import require_user
from alpha_agent.config_store import set_config

router = APIRouter(prefix="/api/evolution", tags=["evolution"])


def _decode_jsonb(value: Any) -> Any:
    """Return a decoded Python object from an asyncpg jsonb column.

    asyncpg typically returns jsonb as an already-decoded dict/list, but
    when the JSON codec is not registered it comes back as str.  Mirror the
    defensive pattern used in alerts.py (_parse_payload).
    """
    if isinstance(value, str):
        return json.loads(value)
    return value


@router.get("/ic_trend")
async def ic_trend(window_days: int = Query(30, ge=1, le=365)) -> dict[str, Any]:
    """IC time-series for every signal over the requested rolling window."""
    pool = await get_db_pool()
    since = datetime.now(UTC) - timedelta(days=window_days)
    rows = await pool.fetch(
        "SELECT signal_name, computed_at, ic, n_observations "
        "FROM signal_ic_history WHERE window_days = $1 AND computed_at >= $2 "
        "ORDER BY signal_name, computed_at",
        window_days,
        since,
    )
    series: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        series.setdefault(r["signal_name"], []).append(
            {
                "computed_at": r["computed_at"].isoformat(),
                "ic": float(r["ic"]),
                "n": int(r["n_observations"]),
            }
        )
    return {
        "window_days": window_days,
        "series": [{"signal_name": k, "points": v} for k, v in series.items()],
    }


@router.get("/ic_annotations")
async def ic_annotations(
    window_days: int = Query(30, ge=1, le=365),
) -> dict[str, Any]:
    """Traceability overlay for the IC chart: the material day-over-day IC
    moves with their structured, correlation-grounded facts. Unauthed read,
    matching the other /api/evolution GETs."""
    from alpha_agent.evolution.metric_annotations import fetch_ic_annotations

    pool = await get_db_pool()
    return {"annotations": await fetch_ic_annotations(pool, window_days)}


@router.post("/_compute_ic_annotations")
async def compute_ic_annotations_endpoint(
    window_days: int = Query(30, ge=1, le=365),
    user_id: int = Depends(require_user),
) -> dict[str, Any]:
    """One-time/admin trigger to (re)compute IC change annotations from
    signal_ic_history. Idempotent. Cron wiring is a follow-up; for now this
    is invoked manually like the other admin maintenance endpoints."""
    from alpha_agent.evolution.metric_annotations import compute_ic_annotations

    pool = await get_db_pool()
    written = await compute_ic_annotations(pool, window_days)
    return {"window_days": window_days, "written": written}


@router.get("/weights")
async def weights() -> dict[str, Any]:
    """Current live + shadow weights for every signal."""
    pool = await get_db_pool()
    rows = await pool.fetch(
        "SELECT signal_name, status, weight, reason, consecutive_bad_windows, "
        "shadow_streak, last_updated FROM signal_weight_current "
        "ORDER BY signal_name, status"
    )
    return {
        "weights": [
            {
                "signal_name": r["signal_name"],
                "status": r["status"],
                "weight": float(r["weight"]),
                "reason": r["reason"],
                "consecutive_bad_windows": r["consecutive_bad_windows"],
                "shadow_streak": r["shadow_streak"],
                "last_updated": (
                    r["last_updated"].isoformat() if r["last_updated"] else None
                ),
            }
            for r in rows
        ]
    }


@router.get("/calibration")
async def calibration() -> dict[str, Any]:
    """Most-recent confidence-calibration snapshot (isotonic map + buckets)."""
    pool = await get_db_pool()
    row = await pool.fetchrow(
        "SELECT as_of, isotonic_map, buckets, n_pairs, applied "
        "FROM confidence_calibration ORDER BY as_of DESC LIMIT 1"
    )
    if row is None:
        return {"as_of": None, "n_pairs": 0, "applied": False, "buckets": []}
    return {
        "as_of": row["as_of"].isoformat(),
        "n_pairs": row["n_pairs"],
        "applied": row["applied"],
        "isotonic_map": _decode_jsonb(row["isotonic_map"]),
        "buckets": _decode_jsonb(row["buckets"]),
    }


@router.get("/changes")
async def changes(
    limit: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    """Recent signal-weight config changes (auto_promote / auto_rollback / etc.)."""
    pool = await get_db_pool()
    rows = await pool.fetch(
        "SELECT id, field, old_value, new_value, changed_at, source, rollback_of "
        "FROM config_change_log WHERE field = 'signal_weights' "
        "ORDER BY changed_at DESC LIMIT $1",
        limit,
    )
    return {
        "changes": [
            {
                "id": r["id"],
                "source": r["source"],
                "changed_at": r["changed_at"].isoformat(),
                "rollback_of": r["rollback_of"],
                "new_value": r["new_value"],
            }
            for r in rows
        ]
    }


# ---------------------------------------------------------------------------
# Phase 2b: human-gated approval layer for methodology proposals
# ---------------------------------------------------------------------------


@router.get("/proposals")
async def proposals() -> dict[str, Any]:
    """List all pending methodology proposals from the proposer."""
    pool = await get_db_pool()
    rows = await pool.fetch(
        "SELECT id, field, old_value, new_value, evidence, changed_at, status "
        "FROM config_change_log WHERE status = 'pending' ORDER BY changed_at DESC"
    )
    return {
        "proposals": [
            {
                "id": r["id"],
                "field": r["field"],
                "old_value": _decode_jsonb(r["old_value"]) if r["old_value"] else None,
                "new_value": _decode_jsonb(r["new_value"]),
                "evidence": _decode_jsonb(r["evidence"]) if r["evidence"] else {},
                "changed_at": r["changed_at"].isoformat(),
                "status": r["status"],
            }
            for r in rows
        ]
    }


@router.post("/proposals/{proposal_id}/approve")
async def approve(
    proposal_id: int,
    user_id: int = Depends(require_user),
) -> dict[str, Any]:
    """Apply the proposed knob change and mark the proposal approved."""
    pool = await get_db_pool()
    row = await pool.fetchrow(
        "SELECT field, new_value FROM config_change_log WHERE id=$1 AND status='pending'",
        proposal_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="proposal not found or not pending")
    new_value = _decode_jsonb(row["new_value"])
    await set_config(pool, row["field"], new_value, user_id=user_id, source="approved")
    await pool.execute(
        "UPDATE config_change_log SET status='approved' WHERE id=$1",
        proposal_id,
    )
    return {"ok": True, "applied": {row["field"]: new_value}}


@router.post("/proposals/{proposal_id}/reject")
async def reject(
    proposal_id: int,
    user_id: int = Depends(require_user),
) -> dict[str, Any]:
    """Mark the proposal rejected without applying any config change."""
    pool = await get_db_pool()
    status = await pool.execute(
        "UPDATE config_change_log SET status='rejected' WHERE id=$1 AND status='pending'",
        proposal_id,
    )
    # asyncpg returns a command tag like "UPDATE 1"; 0 rows means the proposal
    # was missing or already decided. Surface a 404 instead of a misleading
    # ok=true (mirrors the approve guard).
    if status.rsplit(" ", 1)[-1] == "0":
        raise HTTPException(404, "proposal not found or not pending")
    return {"ok": True}


@router.post("/proposals/{proposal_id}/rollback")
async def rollback(
    proposal_id: int,
    user_id: int = Depends(require_user),
) -> dict[str, Any]:
    """Re-apply the old_value of an approved proposal, journaling a rollback row."""
    pool = await get_db_pool()
    row = await pool.fetchrow(
        "SELECT field, old_value FROM config_change_log WHERE id=$1 AND status='approved'",
        proposal_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="approved change not found")
    old_value = _decode_jsonb(row["old_value"]) if row["old_value"] else None
    await set_config(pool, row["field"], old_value, user_id=user_id, source="rollback")
    # Tag the new rollback row with rollback_of pointing at the original proposal.
    await pool.execute(
        "UPDATE config_change_log SET rollback_of=$1 "
        "WHERE id=(SELECT max(id) FROM config_change_log WHERE field=$2 AND source='rollback')",
        proposal_id,
        row["field"],
    )
    return {"ok": True, "reverted": {row["field"]: old_value}}
