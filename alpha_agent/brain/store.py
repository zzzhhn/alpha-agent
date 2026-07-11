"""Phase E4: persistence for BRAIN mining results (brain_alphas table)."""
from __future__ import annotations

import json
from datetime import datetime

from alpha_agent.brain.evolution import family_of


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
    self_correlation_adj: float | None = None,
    self_correlation_adj_with: str | None = None,
    detail: str | None = None,
    grade: str | None = None,
    fail_checks: str | None = None,
    retried: bool = False,
    batch_started_at=None,
) -> int:
    """Insert one mining outcome. Returns the new row id.

    Two self-correlations: `self_correlation` is BRAIN's official value (vs ACTIVE
    alphas); `self_correlation_adj` also counts our passed-but-unsubmitted factors.
    `fail_checks` (rejected only) + `retried` explain the outcome for the UI.
    `batch_started_at` tags the mining round for the batch-divider UI."""
    row = await pool.fetchrow(
        "INSERT INTO brain_alphas "
        "(user_id, expression, settings, alpha_id, sharpe, fitness, turnover, "
        " drawdown, returns, margin, self_correlation, self_correlation_with, "
        " self_correlation_adj, self_correlation_adj_with, outcome, detail, grade, "
        " fail_checks, retried, batch_started_at) "
        "VALUES ($1,$2,$3::jsonb,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,"
        " $18,$19,$20) RETURNING id",
        user_id, expression, json.dumps(settings or {}), alpha_id,
        sharpe, fitness, turnover, drawdown, returns, margin,
        self_correlation, self_correlation_with,
        self_correlation_adj, self_correlation_adj_with, outcome, detail, grade,
        fail_checks, retried, batch_started_at,
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
        for k in ("created_at", "submitted_at", "batch_started_at"):
            if d.get(k) is not None:
                d[k] = d[k].isoformat()
        out.append(d)
    return out


_ROW_COLS = (
    "id, expression, settings, alpha_id, sharpe, fitness, turnover, drawdown, "
    "returns, margin, self_correlation, self_correlation_with, "
    "self_correlation_adj, self_correlation_adj_with, outcome, detail, "
    "grade, fail_checks, retried, batch_started_at, created_at, submitted_at, "
    "brain_status"
)

# Whitelisted sort columns (never interpolate user input into SQL).
_SORT_COLS = {
    "created_at", "sharpe", "fitness", "turnover", "drawdown", "self_correlation",
}


def _decode_row(r) -> dict:
    d = dict(r)
    if isinstance(d.get("settings"), str):
        d["settings"] = json.loads(d["settings"])
    for k in ("created_at", "submitted_at", "batch_started_at"):
        if d.get(k) is not None:
            d[k] = d[k].isoformat()
    # Derived economic family — single source of truth for the UI badge + filter.
    d["family"] = family_of(d.get("expression") or "")
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
    family: str | None = None,
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
        # match either the expression text or the BRAIN alpha id (one param, used
        # twice) so the search box finds a factor by its platform code too.
        params.append(f"%{q}%")
        idx = len(params)
        where.append(f"(expression ILIKE ${idx} OR alpha_id ILIKE ${idx})")
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
    sort_col = sort if sort in _SORT_COLS else "created_at"
    direction = "DESC" if descending else "ASC"
    lim = min(max(int(limit), 1), 200)
    off = max(int(offset), 0)

    if family:
        # `family` is derived (evolution.family_of), not a column, so it can't be
        # a SQL predicate. Per-user rows are in the hundreds, so fetch all that
        # match the SQL-expressible filters, classify + filter in Python, then
        # paginate in memory. Keeps family_of the single source of truth (no
        # drift-prone SQL regex) and still returns an accurate total.
        all_rows = await pool.fetch(
            f"SELECT {_ROW_COLS} FROM brain_alphas WHERE {where_sql} "
            f"ORDER BY {sort_col} {direction} NULLS LAST, id DESC",
            *params,
        )
        matched = [
            d for d in (_decode_row(r) for r in all_rows) if d["family"] == family
        ]
        return {"alphas": matched[off:off + lim], "total": len(matched)}

    total = await pool.fetchval(
        f"SELECT count(*) FROM brain_alphas WHERE {where_sql}", *params
    )
    # NULLS LAST so unscored rows (sim_error) don't dominate a metric sort.
    rows = await pool.fetch(
        f"SELECT {_ROW_COLS} FROM brain_alphas WHERE {where_sql} "
        f"ORDER BY {sort_col} {direction} NULLS LAST, id DESC "
        f"LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}",
        *params, lim, off,
    )
    return {"alphas": [_decode_row(r) for r in rows], "total": int(total or 0)}


async def count_brain_alphas_since(pool, user_id: int, *, since: datetime) -> int:
    """Count this user's mining rows created after `since`. Every candidate is
    persisted regardless of outcome (passed/flagged/rejected/sim_error), so this is
    the honest per-candidate progress signal for an in-flight round. `since` is
    anchored to the DB clock at dispatch (see /mine), so there is no serverless-vs-DB
    clock skew to undercount early rows."""
    # Anchor on batch_started_at (round START), not created_at (row creation): when
    # a new round is dispatched while the PREVIOUS one is still finishing (workflow
    # concurrency queues it), the previous round's tail rows have created_at > since
    # but an EARLIER batch, so counting by created_at inflated the new round's
    # progress (e.g. showed 9/12 when the new batch had only 4). The NULL-batch OR
    # keeps counting a current-round row if batch tagging happened to fail.
    n = await pool.fetchval(
        "SELECT count(*) FROM brain_alphas WHERE user_id=$1 "
        "AND (batch_started_at > $2 "
        "     OR (batch_started_at IS NULL AND created_at > $2))",
        user_id, since,
    )
    return int(n or 0)


async def recent_passed_unsubmitted_alpha_ids(
    pool, user_id: int, *, limit: int = 40
) -> list[str]:
    """alpha_ids of the user's recent PASSED, not-yet-submitted mined alphas — the
    set a new round must also stay decorrelated from, so we don't re-pass this
    round's near-duplicates in a later round. Newest first."""
    rows = await pool.fetch(
        "SELECT alpha_id FROM brain_alphas "
        "WHERE user_id=$1 AND outcome='passed' AND submitted_at IS NULL "
        "AND alpha_id IS NOT NULL "
        "ORDER BY created_at DESC LIMIT $2",
        user_id, min(max(int(limit), 1), 200),
    )
    return [r["alpha_id"] for r in rows]


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
    for k in ("created_at", "submitted_at", "batch_started_at"):
        if d.get(k) is not None:
            d[k] = d[k].isoformat()
    return d


async def update_adjusted_self_correlation(
    pool, user_id: int, alpha_id: str, *, value: float, corr_with: str | None
) -> None:
    """Rewrite a mined alpha's ADJUSTED self-correlation (keyed by BRAIN alpha_id,
    scoped to owner). The official `self_correlation` (BRAIN's value) is left
    untouched; only `self_correlation_adj` is reconciled after each round so an
    EARLY passer's value reflects LATER passed-but-unsubmitted factors. Only
    not-yet-submitted rows."""
    await pool.execute(
        "UPDATE brain_alphas "
        "SET self_correlation_adj=$3, self_correlation_adj_with=$4 "
        "WHERE user_id=$1 AND alpha_id=$2 AND submitted_at IS NULL",
        user_id, alpha_id, value, corr_with,
    )


async def update_official_self_correlation(
    pool, user_id: int, alpha_id: str, *, value: float, corr_with: str | None = "BRAIN"
) -> None:
    """Write BRAIN's OFFICIAL self-correlation (the `self_correlation` column) for a
    mined alpha, keyed by alpha_id, scoped to owner, not-yet-submitted only. Used to
    backfill rows recorded before the get_self_correlation empty-200 poll fix, when
    the official value came back None and the UI showed 待定."""
    await pool.execute(
        "UPDATE brain_alphas "
        "SET self_correlation=$3, self_correlation_with=$4 "
        "WHERE user_id=$1 AND alpha_id=$2 AND submitted_at IS NULL",
        user_id, alpha_id, value, corr_with,
    )


async def unsubmitted_alpha_ids_missing_official(
    pool, user_id: int, *, limit: int = 120
) -> list[str]:
    """alpha_ids of the user's not-yet-submitted mined alphas that still lack an
    OFFICIAL self-correlation (passed/flagged first — the review-worthy ones —
    then the rest), newest first. Drives the backfill."""
    rows = await pool.fetch(
        "SELECT alpha_id FROM brain_alphas "
        "WHERE user_id=$1 AND alpha_id IS NOT NULL AND submitted_at IS NULL "
        "AND self_correlation IS NULL "
        "ORDER BY (outcome IN ('passed','flagged')) DESC, created_at DESC "
        "LIMIT $2",
        user_id, min(max(int(limit), 1), 400),
    )
    return [r["alpha_id"] for r in rows]


async def scored_expressions(
    pool, user_id: int, *, limit: int = 800
) -> list[tuple[str, float]]:
    """(expression, sharpe) for the user's scored mining rows, newest first —
    feeds fastexpr.build_field_hints so generation exploits mining history
    (pin winning signs, skip dead fields) instead of re-flipping known coins."""
    rows = await pool.fetch(
        "SELECT expression, sharpe FROM brain_alphas "
        "WHERE user_id=$1 AND sharpe IS NOT NULL "
        # degenerate empty-book sims (all-zero, no positions) say nothing about
        # the field's signal — excluding them keeps dead-field marking honest
        "AND NOT (sharpe = 0 AND coalesce(turnover, 0) = 0) "
        "ORDER BY created_at DESC LIMIT $2",
        user_id, min(max(int(limit), 1), 2000),
    )
    return [(r["expression"], float(r["sharpe"])) for r in rows]


async def passed_unsubmitted_expressions(
    pool, user_id: int, *, limit: int = 200
) -> list[str]:
    """Expressions of the user's passed-but-unsubmitted mined alphas, newest first —
    seeds the per-family representative counts for the #1/#2 saturation cap."""
    rows = await pool.fetch(
        "SELECT expression FROM brain_alphas "
        "WHERE user_id=$1 AND outcome='passed' AND submitted_at IS NULL "
        "AND expression IS NOT NULL ORDER BY created_at DESC LIMIT $2",
        user_id, min(max(int(limit), 1), 400),
    )
    return [r["expression"] for r in rows]


async def sharpe_of_alpha_id(pool, user_id: int, alpha_id: str):
    """Sharpe of one of the user's mined alphas by BRAIN alpha_id (None if
    unknown/not ours). Feeds the 10%%-better escape hatch: BRAIN allows submitting
    a candidate that self-correlates >=0.7 with an existing alpha IF its Sharpe
    beats that alpha's by >=10%%."""
    return await pool.fetchval(
        "SELECT sharpe FROM brain_alphas WHERE user_id=$1 AND alpha_id=$2 "
        "ORDER BY created_at DESC LIMIT 1", user_id, alpha_id,
    )


async def mark_submitted(pool, alpha_row_id: int, *, brain_status: str) -> None:
    """Record that the user submitted this alpha to BRAIN + BRAIN's status."""
    await pool.execute(
        "UPDATE brain_alphas SET submitted_at=now(), brain_status=$2 WHERE id=$1",
        alpha_row_id, brain_status,
    )
