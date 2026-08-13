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
    self_correlation_status: str | None = None,
    detail: str | None = None,
    grade: str | None = None,
    fail_checks: str | None = None,
    retried: bool = False,
    batch_started_at=None,
    run_id: int | None = None,
    blend_parents: list[str] | None = None,
    research_evidence: dict | None = None,
) -> int:
    """Insert one mining outcome. Returns the new row id.

    Two self-correlations: `self_correlation` is BRAIN's official value (vs ACTIVE
    alphas); `self_correlation_adj` also counts our passed-but-unsubmitted factors.
    `fail_checks` (rejected only) + `retried` explain the outcome for the UI.
    `batch_started_at` tags the mining round for the batch-divider UI.
    `blend_parents` is the list of parent expressions when this candidate was
    stitched by a blend round (family_focus == "blend"); None for every other
    candidate. NULL, not the string "null", is written when absent."""
    if self_correlation_status is None:
        if self_correlation is not None:
            self_correlation_status = "ready"
        elif alpha_id is None:
            self_correlation_status = "unavailable"
        elif outcome == "rejected" and fail_checks:
            self_correlation_status = "skipped_prerequisite"
        else:
            self_correlation_status = "pending"
    row = await pool.fetchrow(
        "INSERT INTO brain_alphas "
        "(user_id, expression, settings, alpha_id, sharpe, fitness, turnover, "
        " drawdown, returns, margin, self_correlation, self_correlation_with, "
        " self_correlation_adj, self_correlation_adj_with, outcome, detail, grade, "
        " fail_checks, retried, batch_started_at, run_id, blend_parents, "
        " self_correlation_status, research_evidence) "
        "VALUES ($1,$2,$3::jsonb,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,"
        " $18,$19,$20,$21,$22::jsonb,$23,$24::jsonb) RETURNING id",
        user_id, expression, json.dumps(settings or {}), alpha_id,
        sharpe, fitness, turnover, drawdown, returns, margin,
        self_correlation, self_correlation_with,
        self_correlation_adj, self_correlation_adj_with, outcome, detail, grade,
        fail_checks, retried, batch_started_at, run_id,
        json.dumps(blend_parents) if blend_parents is not None else None,
        self_correlation_status,
        json.dumps(research_evidence) if research_evidence is not None else None,
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
        bp = d.get("blend_parents")
        if isinstance(bp, str):
            bp = json.loads(bp)
        d["blend_parents"] = bp
        d["is_blend"] = bool(bp)
        evidence = d.get("research_evidence")
        if isinstance(evidence, str):
            d["research_evidence"] = json.loads(evidence)
        out.append(d)
    return out


_ROW_COLS = (
    "id, run_id, expression, settings, alpha_id, sharpe, fitness, turnover, drawdown, "
    "returns, margin, self_correlation, self_correlation_with, "
    "self_correlation_adj, self_correlation_adj_with, self_correlation_status, "
    "outcome, detail, "
    "grade, fail_checks, retried, batch_started_at, created_at, submitted_at, "
    "brain_status, blend_parents, research_evidence"
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
    # `is_blend` is derived from blend_parents (never a stored column) so it can
    # never drift from the parent list — NULL/absent means "not a blend".
    bp = d.get("blend_parents")
    if isinstance(bp, str):
        bp = json.loads(bp)
    d["blend_parents"] = bp
    d["is_blend"] = bool(bp)
    evidence = d.get("research_evidence")
    if isinstance(evidence, str):
        d["research_evidence"] = json.loads(evidence)
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
    run_id: int | None = None,
    sort: str = "created_at",
    descending: bool = True,
) -> dict:
    """Server-side paginated + filtered listing for the BRAIN UI. Returns
    {"alphas": [...], "total": N} where total is the count matching the filters
    (for page controls). All filters are optional and combine with AND."""
    where = ["user_id = $1"]
    params: list = [user_id]

    if run_id is not None:
        params.append(int(run_id))
        where.append("run_id = $2")

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
    bp = d.get("blend_parents")
    if isinstance(bp, str):
        bp = json.loads(bp)
    d["blend_parents"] = bp
    d["is_blend"] = bool(bp)
    evidence = d.get("research_evidence")
    if isinstance(evidence, str):
        d["research_evidence"] = json.loads(evidence)
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
        "SET self_correlation=$3, self_correlation_with=$4, "
        "self_correlation_status='ready' "
        "WHERE user_id=$1 AND alpha_id=$2 AND submitted_at IS NULL",
        user_id, alpha_id, value, corr_with,
    )


async def mark_official_self_correlation_unavailable(
    pool, user_id: int, alpha_id: str
) -> None:
    """Record that a bounded official-correlation poll did not become ready.

    Scheduled backfill still retries these rows because the numeric value remains
    NULL; this status only prevents the UI from calling a completed poll pending.
    """
    await pool.execute(
        "UPDATE brain_alphas SET self_correlation_status='unavailable' "
        "WHERE user_id=$1 AND alpha_id=$2 AND self_correlation IS NULL "
        "AND submitted_at IS NULL",
        user_id, alpha_id,
    )


async def priority_alpha_ids_missing_official_for_run(
    pool, user_id: int, run_id: int, *, limit: int = 5
) -> list[str]:
    """High-value rows worth enriching after the simulation loop.

    Passed/flagged rows come first, followed by GOOD-or-better rejected rows.
    This keeps the extra BRAIN traffic bounded while retaining research evidence.
    """
    rows = await pool.fetch(
        "SELECT alpha_id FROM brain_alphas "
        "WHERE user_id=$1 AND run_id=$2 AND alpha_id IS NOT NULL "
        "AND submitted_at IS NULL AND self_correlation IS NULL "
        "AND (outcome IN ('passed','flagged') "
        "     OR upper(coalesce(grade,'')) IN ('GOOD','EXCELLENT','SPECTACULAR')) "
        "ORDER BY (outcome IN ('passed','flagged')) DESC, "
        "CASE upper(coalesce(grade,'')) WHEN 'SPECTACULAR' THEN 3 "
        "WHEN 'EXCELLENT' THEN 2 WHEN 'GOOD' THEN 1 ELSE 0 END DESC, id DESC "
        "LIMIT $3",
        user_id, run_id, min(max(int(limit), 1), 10),
    )
    return [r["alpha_id"] for r in rows]


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
        "ORDER BY (outcome IN ('passed','flagged')) DESC, "
        "CASE upper(coalesce(grade,'')) WHEN 'SPECTACULAR' THEN 3 "
        "WHEN 'EXCELLENT' THEN 2 WHEN 'GOOD' THEN 1 ELSE 0 END DESC, "
        "created_at DESC "
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


async def options_mechanism_evidence(
    pool,
    user_id: int,
    *,
    field_metadata: list[dict] | None = None,
    limit: int = 1000,
) -> dict:
    """Aggregate options outcomes by mechanism and measured research context."""
    from alpha_agent.brain.evolution import options_mechanism_of
    from alpha_agent.brain.hypotheses import research_context_key

    rows = await pool.fetch(
        "SELECT expression, settings, outcome, grade, sharpe, fail_checks, "
        "self_correlation, self_correlation_adj, created_at "
        "FROM brain_alphas WHERE user_id=$1 "
        "AND expression ~ '(implied_volatility|pcr_oi|historical_volatility|breakeven|forward_price)' "
        "ORDER BY created_at DESC LIMIT $2",
        int(user_id), min(max(int(limit), 1), 2000),
    )
    mechanisms: dict[str, dict[str, float | int]] = {}
    contexts: dict[str, dict[str, float | int]] = {}
    good_grades = {"GOOD", "EXCELLENT", "SPECTACULAR"}

    def update(item: dict[str, float | int], row) -> None:
        item["attempts"] = int(item.get("attempts", 0)) + 1
        if str(row["grade"] or "").upper() in good_grades:
            item["good"] = int(item.get("good", 0)) + 1
        if row["outcome"] in {"passed", "flagged"}:
            item["gates_passed"] = int(item.get("gates_passed", 0)) + 1
        if row["outcome"] == "passed":
            item["passed"] = int(item.get("passed", 0)) + 1
        failures = {part.strip() for part in str(row["fail_checks"] or "").split(",")}
        for check, key in (
            ("CONCENTRATED_WEIGHT", "concentrated"),
            ("LOW_SUB_UNIVERSE_SHARPE", "low_sub_universe"),
            ("HIGH_TURNOVER", "high_turnover"),
        ):
            if check in failures:
                item[key] = int(item.get(key, 0)) + 1
        if row["self_correlation"] is not None:
            item["self_corr_checked"] = int(item.get("self_corr_checked", 0)) + 1
            if float(row["self_correlation"]) < 0.70:
                item["self_corr_passed"] = int(item.get("self_corr_passed", 0)) + 1
        if row["sharpe"] is not None:
            item["sharpe_sum"] = float(item.get("sharpe_sum", 0.0)) + float(row["sharpe"])
            item["sharpe_n"] = int(item.get("sharpe_n", 0)) + 1

    for row in rows:
        mechanism = options_mechanism_of(row["expression"] or "")
        settings = row["settings"] or {}
        if isinstance(settings, str):
            settings = json.loads(settings)
        context = research_context_key(
            mechanism, row["expression"] or "", field_metadata or [], settings
        )
        update(mechanisms.setdefault(mechanism, {}), row)
        update(contexts.setdefault(context, {}), row)
    return {"sample_n": len(rows), "mechanisms": mechanisms, "contexts": contexts}


async def options_surrogate_rows(pool, user_id: int, *, limit: int = 1000) -> list[dict]:
    """Chronological training surface for the bounded local options proxy."""
    rows = await pool.fetch(
        "SELECT expression, settings, outcome, grade, fail_checks, "
        "self_correlation, self_correlation_adj, created_at "
        "FROM brain_alphas WHERE user_id=$1 "
        "AND expression ~ '(implied_volatility|pcr_oi|historical_volatility|breakeven|forward_price)' "
        "AND alpha_id IS NOT NULL ORDER BY created_at ASC LIMIT $2",
        int(user_id), min(max(int(limit), 1), 3000),
    )
    out = []
    for row in rows:
        item = dict(row)
        if isinstance(item.get("settings"), str):
            item["settings"] = json.loads(item["settings"])
        out.append(item)
    return out


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


async def blend_source_expressions(pool, user_id: int) -> tuple[list, list]:
    """(passed, near_misses) as [(expression, alpha_id, sharpe)] for the blend
    round: passed = real unsubmitted passers (BRAIN-verdict); near-miss = the
    strongest rejected/flagged (sharpe >= 0.85, not degenerate). Newest first,
    bounded."""
    passed = [
        (r["expression"], r["alpha_id"], float(r["sharpe"]))
        for r in await pool.fetch(
            "SELECT expression, alpha_id, sharpe FROM brain_alphas "
            "WHERE user_id=$1 AND outcome='passed' AND submitted_at IS NULL "
            "AND expression IS NOT NULL AND sharpe IS NOT NULL "
            "ORDER BY sharpe DESC LIMIT 12", user_id)
    ]
    near = [
        (r["expression"], r["alpha_id"], float(r["sharpe"]))
        for r in await pool.fetch(
            "SELECT expression, alpha_id, sharpe FROM brain_alphas "
            "WHERE user_id=$1 AND outcome IN ('rejected','flagged') "
            "AND sharpe >= 0.85 AND coalesce(turnover,0) > 0 "
            "AND expression IS NOT NULL "
            "ORDER BY sharpe DESC LIMIT 30", user_id)
    ]
    return passed, near


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


# ── First-class mining runs ──────────────────────────────────────────────

_RUN_COLS = (
    "id, user_id, source, family_focus, requested_n, generation_target_n, "
    "parent_run_id, generated_n, screened_n, "
    "simulated_n, persisted_n, passed_n, flagged_n, rejected_n, sim_error_n, "
    "status, screen_status, screen_detail, seed, created_at, queued_at, "
    "started_at, completed_at, updated_at, error_detail, github_run_id, "
    "batch_started_at, legacy_batch_started_at"
)
_RUN_MUTABLE_COLS = {
    "family_focus", "requested_n", "generation_target_n", "parent_run_id",
    "generated_n", "screened_n", "simulated_n",
    "persisted_n", "passed_n", "flagged_n", "rejected_n", "sim_error_n",
    "status", "screen_status", "screen_detail", "seed", "started_at",
    "completed_at", "error_detail", "github_run_id", "batch_started_at",
}
_RUN_SOURCES = {"manual", "schedule", "legacy"}


def _decode_run(row) -> dict:
    """Decode an asyncpg run row into the JSON-safe API shape."""
    d = dict(row)
    for key in (
        "created_at", "queued_at", "started_at", "completed_at", "updated_at",
        "batch_started_at", "legacy_batch_started_at",
    ):
        if d.get(key) is not None:
            d[key] = d[key].isoformat()
    # The UI historically called the terminal timestamp ``finished_at``;
    # retain that response alias while the database uses completed_at.
    d["finished_at"] = d.get("completed_at")
    d["outcomes"] = {
        "passed": int(d.get("passed_n") or 0),
        "flagged": int(d.get("flagged_n") or 0),
        "rejected": int(d.get("rejected_n") or 0),
        "sim_error": int(d.get("sim_error_n") or 0),
    }
    return d


async def create_brain_run(
    pool,
    *,
    user_id: int,
    source: str,
    requested_n: int,
    generation_target_n: int | None = None,
    parent_run_id: int | None = None,
    family_focus: str | None = None,
    seed: int | None = None,
    screen_status: str = "pending",
    screen_detail: str | None = None,
    github_run_id: str | int | None = None,
) -> dict:
    """Create a queued BRAIN run and return its decoded row.

    The insert is intentionally separate from GitHub dispatch: callers can
    always retain a failed/manual request as an auditable run object.
    """
    if source not in _RUN_SOURCES:
        raise ValueError(f"invalid BRAIN run source: {source!r}")
    requested = max(0, int(requested_n))
    generation_target = max(
        requested,
        int(generation_target_n) if generation_target_n is not None else requested,
    )
    row = await pool.fetchrow(
        "INSERT INTO brain_runs "
        "(user_id, source, family_focus, requested_n, generation_target_n, "
        " parent_run_id, seed, screen_status, screen_detail, github_run_id) "
        "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10) RETURNING " + _RUN_COLS,
        int(user_id), source, family_focus, requested, generation_target,
        int(parent_run_id) if parent_run_id is not None else None,
        seed, screen_status, screen_detail,
        str(github_run_id) if github_run_id is not None else None,
    )
    return _decode_run(row)


async def get_brain_run(
    pool, run_id: int, user_id: int | None = None
) -> dict | None:
    """Return one run, optionally constrained to its owner."""
    if user_id is None:
        row = await pool.fetchrow(
            f"SELECT {_RUN_COLS} FROM brain_runs WHERE id=$1", int(run_id)
        )
    else:
        row = await pool.fetchrow(
            f"SELECT {_RUN_COLS} FROM brain_runs WHERE id=$1 AND user_id=$2",
            int(run_id), int(user_id),
        )
    return _decode_run(row) if row is not None else None


async def list_brain_runs(
    pool,
    user_id: int,
    *,
    limit: int = 20,
    offset: int = 0,
    status: str | None = None,
) -> dict:
    """List a user's run objects newest first with an accurate total."""
    lim = min(max(int(limit), 1), 100)
    off = max(int(offset), 0)
    where = ["user_id=$1"]
    params: list = [int(user_id)]
    if status:
        params.append(status)
        where.append(f"status=${len(params)}")
    where_sql = " AND ".join(where)
    total = await pool.fetchval(
        f"SELECT count(*) FROM brain_runs WHERE {where_sql}", *params
    )
    rows = await pool.fetch(
        f"SELECT {_RUN_COLS} FROM brain_runs WHERE {where_sql} "
        f"ORDER BY created_at DESC, id DESC LIMIT ${len(params)+1} "
        f"OFFSET ${len(params)+2}",
        *params, lim, off,
    )
    return {"runs": [_decode_run(row) for row in rows], "total": int(total or 0)}


async def update_brain_run(pool, run_id: int, **fields) -> dict | None:
    """Update whitelisted run metadata and return the new row.

    Counters should normally use :func:`increment_brain_run_counts` so parallel
    runner writes remain additive.  This helper is for lifecycle and screen
    metadata where last-write-wins is intentional.
    """
    unknown = set(fields) - _RUN_MUTABLE_COLS
    if unknown:
        raise ValueError(f"unknown BRAIN run fields: {sorted(unknown)}")
    if not fields:
        return await get_brain_run(pool, run_id)
    assignments: list[str] = []
    params: list = [int(run_id)]
    for column, value in fields.items():
        params.append(value)
        assignments.append(f"{column}=${len(params)}")
    assignments.append("updated_at=now()")
    row = await pool.fetchrow(
        f"UPDATE brain_runs SET {', '.join(assignments)} WHERE id=$1 "
        f"RETURNING {_RUN_COLS}",
        *params,
    )
    return _decode_run(row) if row is not None else None


async def mark_brain_run_running(
    pool, run_id: int, *, github_run_id: str | int | None = None
) -> dict | None:
    # Let PostgreSQL supply the first start timestamp while keeping retries from
    # moving the original lifecycle boundary.
    assignments = ["status='running'", "started_at=COALESCE(started_at, now())",
                   "error_detail=NULL", "updated_at=now()"]
    params: list = [int(run_id)]
    if github_run_id is not None:
        params.append(str(github_run_id))
        assignments.append(f"github_run_id=${len(params)}")
    row = await pool.fetchrow(
        f"UPDATE brain_runs SET {', '.join(assignments)} WHERE id=$1 "
        f"RETURNING {_RUN_COLS}",
        *params,
    )
    return _decode_run(row) if row is not None else None


async def complete_brain_run(pool, run_id: int, **counts) -> dict | None:
    """Mark a run completed and optionally set final counter values."""
    fields = {k: v for k, v in counts.items() if k in _RUN_MUTABLE_COLS}
    unknown = set(counts) - set(fields)
    if unknown:
        raise ValueError(f"unknown BRAIN run fields: {sorted(unknown)}")
    assignments = ["status='completed'", "completed_at=now()", "updated_at=now()"]
    params: list = [int(run_id)]
    for column, value in fields.items():
        params.append(value)
        assignments.append(f"{column}=${len(params)}")
    row = await pool.fetchrow(
        f"UPDATE brain_runs SET {', '.join(assignments)} WHERE id=$1 "
        f"RETURNING {_RUN_COLS}",
        *params,
    )
    return _decode_run(row) if row is not None else None


async def fail_brain_run(
    pool, run_id: int, *, error_detail: str, **counts
) -> dict | None:
    """Mark a run failed while preserving any counters collected so far."""
    fields = {k: v for k, v in counts.items() if k in _RUN_MUTABLE_COLS}
    unknown = set(counts) - set(fields)
    if unknown:
        raise ValueError(f"unknown BRAIN run fields: {sorted(unknown)}")
    assignments = ["status='failed'", "completed_at=now()", "error_detail=$2",
                   "updated_at=now()"]
    params: list = [int(run_id), str(error_detail)]
    for column, value in fields.items():
        params.append(value)
        assignments.append(f"{column}=${len(params)}")
    row = await pool.fetchrow(
        f"UPDATE brain_runs SET {', '.join(assignments)} WHERE id=$1 "
        f"RETURNING {_RUN_COLS}",
        *params,
    )
    return _decode_run(row) if row is not None else None


async def set_brain_run_progress(pool, run_id: int, **fields) -> dict | None:
    """Set generated/screened counters and screen truth during a run."""
    allowed = {
        "generated_n", "screened_n", "screen_status", "screen_detail",
        "requested_n", "generation_target_n", "seed", "family_focus",
        "batch_started_at",
    }
    unknown = set(fields) - allowed
    if unknown:
        raise ValueError(f"unknown BRAIN progress fields: {sorted(unknown)}")
    return await update_brain_run(pool, run_id, **fields)


async def increment_brain_run_counts(
    pool,
    run_id: int,
    *,
    simulated: int = 0,
    persisted: int = 0,
    passed: int = 0,
    flagged: int = 0,
    rejected: int = 0,
    sim_error: int = 0,
) -> dict | None:
    """Atomically add per-candidate progress/outcome counts to a run."""
    values = [simulated, persisted, passed, flagged, rejected, sim_error]
    if any(int(v) < 0 for v in values):
        raise ValueError("BRAIN run increments must be non-negative")
    row = await pool.fetchrow(
        "UPDATE brain_runs SET "
        "simulated_n=simulated_n+$2, persisted_n=persisted_n+$3, "
        "passed_n=passed_n+$4, flagged_n=flagged_n+$5, "
        "rejected_n=rejected_n+$6, sim_error_n=sim_error_n+$7, "
        "updated_at=now() WHERE id=$1 RETURNING " + _RUN_COLS,
        int(run_id), int(simulated), int(persisted), int(passed), int(flagged),
        int(rejected), int(sim_error),
    )
    return _decode_run(row) if row is not None else None
