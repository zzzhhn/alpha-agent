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
    returns: float | None = None,
    margin: float | None = None,
    self_correlation: float | None = None,
    self_correlation_with: str | None = None,
    detail: str | None = None,
) -> int:
    """Insert one mining outcome. Returns the new row id."""
    row = await pool.fetchrow(
        "INSERT INTO brain_alphas "
        "(user_id, expression, settings, alpha_id, sharpe, fitness, turnover, "
        " drawdown, returns, margin, self_correlation, self_correlation_with, "
        " outcome, detail) "
        "VALUES ($1,$2,$3::jsonb,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14) RETURNING id",
        user_id, expression, json.dumps(settings or {}), alpha_id,
        sharpe, fitness, turnover, drawdown, returns, margin,
        self_correlation, self_correlation_with, outcome, detail,
    )
    return row["id"]


async def list_brain_alphas(pool, user_id: int, *, limit: int = 100) -> list[dict]:
    """Recent mining results for a user, newest first, jsonb decoded."""
    rows = await pool.fetch(
        f"SELECT {_ROW_COLS} "
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


_ROW_COLS = (
    "id, expression, settings, alpha_id, sharpe, fitness, turnover, drawdown, "
    "returns, margin, self_correlation, self_correlation_with, outcome, detail, "
    "created_at, submitted_at, brain_status"
)

# Whitelisted sort columns (never interpolate user input into SQL).
_SORT_COLS = {
    "created_at", "sharpe", "fitness", "turnover", "drawdown", "self_correlation",
}


def _decode_row(r) -> dict:
    d = dict(r)
    if isinstance(d.get("settings"), str):
        d["settings"] = json.loads(d["settings"])
    for k in ("created_at", "submitted_at"):
        if d.get(k) is not None:
            d[k] = d[k].isoformat()
    return d


async def query_brain_alphas(
    pool,
    user_id: int,
    *,
    limit: int = 25,
    offset: int = 0,
    outcome: str | None = None,
    q: str | None = None,
    sharpe_min: float | None = None,
    fitness_min: float | None = None,
    turnover_max: float | None = None,
    submitted: bool | None = None,
    sort: str = "created_at",
    descending: bool = True,
) -> dict:
    """Server-side paginated + filtered listing for the BRAIN UI. Returns
    {"alphas": [...], "total": N} where total is the count matching the filters
    (for page controls). All filters are optional and combine with AND."""
    where = ["user_id = $1"]
    params: list = [user_id]

    def add(clause: str, value) -> None:
        params.append(value)
        where.append(clause.replace("$?", f"${len(params)}"))

    if outcome:
        add("outcome = $?", outcome)
    if q:
        add("expression ILIKE $?", f"%{q}%")
    if sharpe_min is not None:
        add("sharpe >= $?", sharpe_min)
    if fitness_min is not None:
        add("fitness >= $?", fitness_min)
    if turnover_max is not None:
        add("turnover <= $?", turnover_max)
    if submitted is True:
        where.append("submitted_at IS NOT NULL")
    elif submitted is False:
        where.append("submitted_at IS NULL")

    where_sql = " AND ".join(where)
    total = await pool.fetchval(
        f"SELECT count(*) FROM brain_alphas WHERE {where_sql}", *params
    )

    sort_col = sort if sort in _SORT_COLS else "created_at"
    direction = "DESC" if descending else "ASC"
    lim = min(max(int(limit), 1), 200)
    off = max(int(offset), 0)
    # NULLS LAST so unscored rows (sim_error) don't dominate a metric sort.
    rows = await pool.fetch(
        f"SELECT {_ROW_COLS} FROM brain_alphas WHERE {where_sql} "
        f"ORDER BY {sort_col} {direction} NULLS LAST, id DESC "
        f"LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}",
        *params, lim, off,
    )
    return {"alphas": [_decode_row(r) for r in rows], "total": int(total or 0)}


async def get_brain_alpha(pool, user_id: int, row_id: int) -> dict | None:
    """One mining result by id, scoped to the owner (None if not found / not
    theirs). jsonb settings decoded."""
    r = await pool.fetchrow(
        f"SELECT {_ROW_COLS} FROM brain_alphas WHERE id=$1 AND user_id=$2",
        row_id, user_id,
    )
    if r is None:
        return None
    d = dict(r)
    if isinstance(d.get("settings"), str):
        d["settings"] = json.loads(d["settings"])
    for k in ("created_at", "submitted_at"):
        if d.get(k) is not None:
            d[k] = d[k].isoformat()
    return d


async def mark_submitted(pool, alpha_row_id: int, *, brain_status: str) -> None:
    """Record that the user submitted this alpha to BRAIN + BRAIN's status."""
    await pool.execute(
        "UPDATE brain_alphas SET submitted_at=now(), brain_status=$2 WHERE id=$1",
        alpha_row_id, brain_status,
    )
