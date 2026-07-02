"""Phase E4: persistence for BRAIN mining results (brain_alphas table)."""
from __future__ import annotations

import json


async def record_brain_alpha(
    pool,
    *,
    user_id: int,
    expression: str,
    settings: dict,
    outcome: str,
    alpha_id: str | None = None,
    sharpe: float | None = None,
    fitness: float | None = None,
    turnover: float | None = None,
    drawdown: float | None = None,
    self_correlation: float | None = None,
    self_correlation_with: str | None = None,
    detail: str | None = None,
) -> int:
    """Insert one mining outcome. Returns the new row id."""
    row = await pool.fetchrow(
        "INSERT INTO brain_alphas "
        "(user_id, expression, settings, alpha_id, sharpe, fitness, turnover, "
        " drawdown, self_correlation, self_correlation_with, outcome, detail) "
        "VALUES ($1,$2,$3::jsonb,$4,$5,$6,$7,$8,$9,$10,$11,$12) RETURNING id",
        user_id, expression, json.dumps(settings or {}), alpha_id,
        sharpe, fitness, turnover, drawdown,
        self_correlation, self_correlation_with, outcome, detail,
    )
    return row["id"]


async def list_brain_alphas(pool, user_id: int, *, limit: int = 100) -> list[dict]:
    """Recent mining results for a user, newest first, jsonb decoded."""
    rows = await pool.fetch(
        "SELECT id, expression, settings, alpha_id, sharpe, fitness, turnover, "
        "drawdown, self_correlation, self_correlation_with, outcome, detail, "
        "created_at, submitted_at, brain_status "
        "FROM brain_alphas WHERE user_id=$1 ORDER BY created_at DESC LIMIT $2",
        user_id, min(max(int(limit), 1), 500),
    )
    out: list[dict] = []
    for r in rows:
        d = dict(r)
        settings = d.get("settings")
        if isinstance(settings, str):
            d["settings"] = json.loads(settings)
        for k in ("created_at", "submitted_at"):
            if d.get(k) is not None:
                d[k] = d[k].isoformat()
        out.append(d)
    return out


async def mark_submitted(pool, alpha_row_id: int, *, brain_status: str) -> None:
    """Record that the user submitted this alpha to BRAIN + BRAIN's status."""
    await pool.execute(
        "UPDATE brain_alphas SET submitted_at=now(), brain_status=$2 WHERE id=$1",
        alpha_row_id, brain_status,
    )
