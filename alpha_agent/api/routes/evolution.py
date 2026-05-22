"""Read-only Evolution self-analysis endpoints.

Surfaces data already produced by the self-loop (Phases 1a/1b/1c) for the
/evolution dashboard. No writes, no analysis logic. Mirrors health.py style.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Query

from alpha_agent.api.dependencies import get_db_pool

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
