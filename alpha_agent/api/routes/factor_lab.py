"""Phase 3c factor-lab admin endpoints.

GET  /api/factor-lab/diagnostic - the propose-time input snapshot. Unauthed
                                  read (matches the unauthed /api/evolution
                                  reads from Phase 2c).
POST /api/factor-lab/propose    - run the propose loop (diagnostic + BYOK LLM
                                  + canned tests + purged WF + DSR-lite) and
                                  write surviving candidates as pending rows
                                  to factor_proposals. Admin auth required.

Cost-guard: BEFORE the BYOK LLM call, check daily_prices history; if below
the validator's MIN_FOLDS threshold the endpoint returns dormant=true
without paying for the LLM call. Forgiveness UX: do not waste user tokens
on a deploy that cannot produce a valid result."""
from __future__ import annotations

import json
import logging
import os

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException, Request

from alpha_agent.api.byok import get_llm_client
from alpha_agent.api.dependencies import get_db_pool
from alpha_agent.auth.dependencies import require_user
from alpha_agent.config_store import refresh_config, set_config
from alpha_agent.core.factor_ast import refresh_allowed_ops
from alpha_agent.evolution.correlation_gate import (
    SELF_CORR_THRESHOLD,
    SelfCorrelationGate,
)
from alpha_agent.evolution.diagnostics import compute_diagnostic
from alpha_agent.evolution.factor_validation import evaluate_factor_candidate
from alpha_agent.evolution.llm_factor_proposer import RawProposal, propose_factors
from alpha_agent.evolution.sandbox import SandboxRunner
from alpha_agent.evolution.skeptic import assess_candidate
from alpha_agent.evolution.validation import deflated_sharpe_lite
from alpha_agent.storage import factor_lessons, propose_jobs

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/factor-lab", tags=["factor_lab"])

# Cost-guard threshold: roughly 3 folds * 30 test days * 10 tickers = 900 rows.
# Below this, the validator cannot produce MIN_FOLDS folds, so the LLM call
# would be wasted; return dormant immediately.
_MIN_HISTORY_ROWS = 1000

# Relaxed thresholds (2026-05-25): previously both r_mean > base_mean AND
# defl > 0 were hard gates; that filtered 100% of Kimi's proposals every
# run. User decision: keep a filter but loosen so marginal candidates
# reach human review. Human is the final gate; surfacing more candidates
# surfaces more learning even if approval rate drops. Dialed back from
# the emergency-debug 0.3/-3.0 once end-to-end pipeline confirmed working.
_BASE_RATIO = 0.6           # accept r_mean within 60% of baseline Sharpe
_DSR_THRESHOLD = -1.0       # deflated Sharpe down to -1.0 keeps marginal candidates visible
# Cap the skeptic LLM reviews per round: only the top few survivors get a
# second opinion, keeping the extra latency inside the propose time budget.
_SKEPTIC_MAX = 3


@router.get("/diagnostic")
async def get_diagnostic(pool=Depends(get_db_pool)) -> dict:
    # config_store keeps a process-level cache; on a fresh lambda instance the
    # cache is empty and _resolve_default_expr() falls back to DEFAULTS even
    # when factor.custom_expression has been written to the DB by another
    # instance (manual edit or approve). Refresh at request entry so the
    # diagnostic reads what every other lambda has already persisted.
    await refresh_config(pool)
    d = await compute_diagnostic(pool)
    return d.to_jsonable()


@router.get("/lessons")
async def get_lessons(limit: int = 20, pool=Depends(get_db_pool)) -> dict:
    """Recent mining-journal lessons for the /evolution Mining Journal panel.

    Unauthed read (matches /diagnostic). Degrades to an empty list if the
    factor_lessons table hasn't been migrated yet (V027 not applied)."""
    try:
        rows = await pool.fetch(
            "SELECT created_at, expression, outcome, test_sharpe, test_ic, "
            "deflated_sharpe, reject_reason, lesson FROM factor_lessons "
            "ORDER BY created_at DESC LIMIT $1",
            min(max(int(limit), 1), 100),
        )
    except Exception as e:  # noqa: BLE001 - table may not exist yet
        logger.warning("get_lessons query failed (table missing?): %s", e)
        return {"lessons": []}
    return {"lessons": [dict(r) for r in rows]}


async def _run_propose_work(
    pool, user_id: int, n: int, diagnostic
) -> dict:
    """The actual propose loop: LLM call + per-candidate validation + DSR
    scoring + pending-row writes. Returns the result dict the old sync
    endpoint used to return inline.

    Pre-conditions checked by the caller:
      - refresh_config(pool) already ran
      - cost-guard passed (history rows >= _MIN_HISTORY_ROWS)
      - diagnostic is the snapshot captured BEFORE LLM call so the LLM
        rationale references the same baseline that drives the threshold

    Raises asyncio.TimeoutError / ValueError on LLM-layer failure; caller
    is responsible for mapping those onto the job row's failed state."""
    import numpy as np

    # Phase A: inject the experiment-journal memory (recent lessons + already-
    # tried expressions) so the proposer stops repeating rejects and shifts
    # direction. Best-effort: a memory-read failure must not block a propose.
    try:
        lessons = await factor_lessons.load_recent_lessons(pool, limit=12)
        tried = await factor_lessons.load_tried_expressions(pool, limit=30)
    except Exception as e:  # noqa: BLE001 - memory is auxiliary to the propose
        logger.warning("factor_lessons load failed; proposing without memory: %s", e)
        lessons, tried = [], []

    llm_client = await get_llm_client(user_id=user_id)
    raw_proposals = await propose_factors(
        llm_client, diagnostic, n=n, lessons=lessons, tried_expressions=tried,
    )
    if not raw_proposals:
        return {"evaluated": 0, "proposed": 0, "dormant": False}

    runner = SandboxRunner()
    # Collect every rejection reason from evaluate_factor_candidate so the
    # response body can surface why each candidate failed. Without this, all
    # three early-return branches below emit only `{evaluated, proposed,
    # dormant}` (44 bytes) and the user sees "0/5 proposed" with no signal.
    rejects: list = []
    try:
        # 1. Evaluate each candidate (canned tests + purged WF)
        results = []
        for proposal in raw_proposals:
            r = await evaluate_factor_candidate(
                pool, runner, proposal, out_rejects=rejects
            )
            if r is not None:
                results.append(r)
        if not results:
            return {
                "evaluated": len(raw_proposals),
                "proposed": 0,
                "dormant": False,
                "_diag": {"rejects": rejects},
            }

        # 2. Baseline: re-evaluate current expression for comparison.
        baseline = await evaluate_factor_candidate(
            pool, runner,
            RawProposal(expression=diagnostic.current_expression, new_operators=[]),
            out_rejects=rejects,
        )
        if baseline is None:
            return {
                "evaluated": len(raw_proposals),
                "proposed": 0,
                "dormant": True,
                "_diag": {"rejects": rejects, "baseline_rejected": True},
            }

        # 3. DSR-lite deflation: keep only survivors that beat baseline AND
        #    have post-deflation positive Sharpe.
        all_means = [float(np.mean(r.sharpes)) for r in results]
        base_mean = float(np.mean(baseline.sharpes))
        proposed_count = 0
        skeptic_used = 0

        # Phase B1: the SELF_CORRELATION gate re-evaluates every saved factor on
        # the full panel — the heaviest work in a propose round. Build it LAZILY,
        # only once a candidate actually survives the DSR gate, so the common
        # 0-survivor round never pays for it (and never risks blowing the Vercel
        # function budget on a check that nothing needs). A survivor whose daily
        # long-short PnL is ~the same as a saved factor is a re-discovery, not a
        # new alpha (WorldQuant SELF_CORRELATION analog); empty saved set / any
        # load failure → the gate is a harmless no-op.
        _corr_gate: SelfCorrelationGate | None = None

        def _corr_check(expression: str) -> tuple[float, str | None]:
            nonlocal _corr_gate
            if _corr_gate is None:
                try:
                    from alpha_agent.storage.factor_db import list_factors

                    saved = [
                        (f.get("name") or f.get("id") or "saved", f["expression"])
                        for f in list_factors(limit=40)
                        if f.get("expression") and not f.get("last_overfit_flag")
                    ]
                except Exception as e:  # noqa: BLE001 - gate is auxiliary
                    logger.warning("list_factors for self-corr gate failed: %s", e)
                    saved = []
                _corr_gate = SelfCorrelationGate(saved)
            return _corr_gate.check(expression)
        # Per-candidate decision trail returned in the response body so the
        # client can see why each candidate did/didn't make it. More reliable
        # than stderr emit because Vercel CLI logs sometimes only surface the
        # first stderr line per lambda invocation.
        diag_candidates: list[dict] = []
        for r in sorted(results, key=lambda r: -float(np.mean(r.sharpes))):
            r_mean = float(np.mean(r.sharpes))
            defl = deflated_sharpe_lite(r_mean, all_means, len(raw_proposals))
            passes_mean = r_mean > base_mean * _BASE_RATIO
            passes_defl = defl > _DSR_THRESHOLD
            accepted = passes_mean and passes_defl

            # Phase B1: only survivors are worth the (panel-backed) correlation
            # check. A too-high match with a saved factor flips accept→reject
            # (it's a re-discovery, not new alpha).
            self_corr = 0.0
            corr_with: str | None = None
            redundant = False
            if accepted:
                self_corr, corr_with = _corr_check(r.expression)
                if self_corr >= SELF_CORR_THRESHOLD:
                    redundant = True
                    accepted = False

            diag_candidates.append({
                "expression": r.expression[:120],
                "r_mean": r_mean,
                "defl": defl,
                "passes_mean": passes_mean,
                "passes_defl": passes_defl,
                "self_correlation": self_corr,
                "self_correlation_with": corr_with,
                "redundant": redundant,
            })

            if accepted:
                rationale = next(
                    (p.rationale for p in raw_proposals if p.expression == r.expression),
                    "",
                )
                # Phase B2: a SEPARATE skeptic LLM reviews the top survivors and
                # flags look-good-but-risky. It never blocks (human is the final
                # gate); assess_candidate returns None on any failure.
                skeptic_json = None
                if skeptic_used < _SKEPTIC_MAX:
                    verdict = await assess_candidate(
                        llm_client,
                        r.expression,
                        {
                            "sharpes": r.sharpes,
                            "ic_oos": r.ic_oos,
                            "deflated_sharpe": defl,
                            "self_correlation": self_corr,
                            "self_correlation_with": corr_with,
                        },
                    )
                    skeptic_used += 1
                    skeptic_json = verdict.to_jsonable() if verdict else None
                await pool.execute(
                    "INSERT INTO factor_proposals "
                    "(status, expression, new_operators, evidence, diagnostic) "
                    "VALUES ('pending', $1, $2::jsonb, $3::jsonb, $4::jsonb)",
                    r.expression,
                    json.dumps(r.new_operators),
                    json.dumps({
                        "sharpes": r.sharpes,
                        "ic_oos": r.ic_oos,
                        "deflated_sharpe": defl,
                        "baseline_sharpe": base_mean,
                        "n_folds": r.n_folds,
                        "n_trials": len(raw_proposals),
                        "llm_rationale": rationale,
                        "operator_test_results": r.operator_test_results,
                        "self_correlation": self_corr,
                        "self_correlation_with": corr_with,
                        "skeptic": skeptic_json,
                    }),
                    json.dumps(diagnostic.to_jsonable()),
                )
                proposed_count += 1

            # Phase A/B: journal this candidate's outcome so future rounds learn.
            # accepted = kept; redundant = rejected (self-correlation); else
            # weak. Best-effort — never fail a propose over a memory write.
            _ic = float(r.ic_oos) if r.ic_oos is not None else None
            if accepted:
                _outcome, _reject = "accepted", None
            elif redundant:
                _outcome = "rejected"
                _reject = f"redundant: self-corr {self_corr:.2f} vs {corr_with}"
            else:
                _outcome, _reject = "weak", None
            try:
                await factor_lessons.record_lesson(
                    pool,
                    expression=r.expression,
                    outcome=_outcome,
                    test_sharpe=r_mean,
                    test_ic=_ic,
                    deflated_sharpe=defl,
                    reject_reason=_reject,
                )
            except Exception as e:  # noqa: BLE001 - memory is auxiliary
                logger.warning("factor_lessons record (candidate) failed: %s", e)

        # Journal rejected candidates (canned-test / degenerate / too-few-folds)
        # so the proposer learns which structures and errors to avoid.
        for rj in rejects:
            try:
                await factor_lessons.record_lesson(
                    pool,
                    expression=rj.get("expression", ""),
                    outcome="rejected",
                    reject_reason=rj.get("reason"),
                )
            except Exception as e:  # noqa: BLE001 - memory is auxiliary
                logger.warning("factor_lessons record (rejected) failed: %s", e)

        return {
            "evaluated": len(raw_proposals),
            "proposed": proposed_count,
            "dormant": False,
            "_diag": {
                "base_mean": base_mean,
                "base_threshold": base_mean * _BASE_RATIO,
                "defl_threshold": _DSR_THRESHOLD,
                "candidates": diag_candidates,
                "rejects": rejects,
            },
        }
    finally:
        runner.close()


_GH_REPO = os.environ.get("GH_REPO", "zzzhhn/alpha-agent")
_GH_REF = os.environ.get("GH_REF", "main")
_PROPOSE_RUNNER_WORKFLOW = "propose-job-runner.yml"


async def _dispatch_propose_runner() -> None:
    """Best-effort: kick the GitHub Actions job-runner so a freshly-queued
    propose job starts within ~1min instead of waiting for the runner's fallback
    schedule. Never raises — a dispatch failure only delays the job (the
    scheduled runner still drains it), it never drops it.

    We do NOT use a FastAPI BackgroundTask: Vercel freezes the function once the
    response is sent, so post-response work never runs. That is exactly why the
    button silently produced nothing after the 2026-05-26 async refactor. The
    reliable path is a GitHub Actions runner calling /api/cron/run_propose_jobs,
    which executes the work in-request (server-to-server, no browser long-hold)."""
    gh_token = os.environ.get("GH_PAT")
    if not gh_token:
        logger.warning(
            "GH_PAT missing; queued propose job waits for the scheduled runner"
        )
        return
    url = (
        f"https://api.github.com/repos/{_GH_REPO}/actions/"
        f"workflows/{_PROPOSE_RUNNER_WORKFLOW}/dispatches"
    )
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                url,
                json={"ref": _GH_REF},
                headers={
                    "Authorization": f"Bearer {gh_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
        if resp.status_code != 204:
            logger.warning(
                "propose runner dispatch returned %s: %s",
                resp.status_code, resp.text[:200],
            )
    except Exception as e:  # noqa: BLE001 — dispatch is best-effort
        logger.warning("propose runner dispatch failed: %s", e)


@router.post("/propose")
async def post_propose(
    body: dict = Body(default_factory=dict),
    user_id: int = Depends(require_user),
    pool=Depends(get_db_pool),
) -> dict:
    """Enqueue a propose job and return 202 immediately with a job_id.

    The work does NOT run here. A GitHub Actions runner (kicked instantly via
    workflow_dispatch below, plus a fallback schedule) calls
    /api/cron/run_propose_jobs, which runs the LLM call + per-candidate
    validation + DSR scoring in-request and writes the terminal job state. The
    frontend polls GET /jobs/{id} every 3s until done|failed.

    Why not a FastAPI BackgroundTask (the 2026-05-26 design): Vercel freezes the
    function after the response is sent, so post-response work never completed
    and the button silently produced nothing. Why not a synchronous POST (the
    pre-2026-05-26 design): under China egress + local TUN proxy the 30-180s
    connection was dropped mid-response. Enqueue + reliable runner + short poll
    GETs sidesteps both.

    Dormant short-circuit (history below cost-guard) still returns 200 + a
    synthetic 'done' job inline so the client skips the poll entirely."""
    n = int(body.get("n", 5)) if isinstance(body, dict) else 5
    n = max(1, min(n, 20))  # input sanitization at the boundary

    # Same cache-refresh rationale as get_diagnostic: the cost-guard + the
    # runner's baseline route through the process-cache; refresh so a manual
    # edit from another lambda instance is visible.
    await refresh_config(pool)

    # Cost-guard: skip the whole pipeline if history is too thin to validate
    # anything. Synthesize a 'done' job inline so the poll completes in one
    # round-trip rather than dispatching a runner for a known-empty result.
    history_n = await pool.fetchval("SELECT count(*) FROM daily_prices") or 0
    if history_n < _MIN_HISTORY_ROWS:
        dormant_result = {"evaluated": 0, "proposed": 0, "dormant": True}
        job_id = await propose_jobs.create_job(pool, user_id, n)
        await propose_jobs.mark_done(pool, job_id, dormant_result)
        return {"job_id": job_id, "status": "done", "inline_result": dormant_result}

    job_id = await propose_jobs.create_job(pool, user_id, n)
    # Kick the runner now (best-effort); the fallback schedule covers a miss.
    await _dispatch_propose_runner()
    return {"job_id": job_id, "status": "queued"}


@router.get("/jobs/{job_id}")
async def get_propose_job(
    job_id: str,
    user_id: int = Depends(require_user),
    pool=Depends(get_db_pool),
) -> dict:
    """Poll endpoint for the propose job state. Returns the row keyed
    by job_id. 404 if not found; 403 if owned by a different user.

    Polled by the frontend every 3s for up to 5min. Each call is short
    (<100ms typical) so even an unstable connection has 100 chances to
    succeed before the client gives up."""
    job = await propose_jobs.get_job(pool, job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    if job["user_id"] != user_id:
        raise HTTPException(403, "not your job")
    return job


@router.post("/_apply_migrations")
async def post_apply_migrations(
    user_id: int = Depends(require_user),
) -> dict:
    """One-time admin trigger to apply pending DB migrations (V017+).

    Vercel deploys don't auto-run migrations and the user can't direct-
    connect to Neon from China egress, so the migration step has to
    happen via the backend itself. apply_migrations() is idempotent
    (schema_migrations table tracks applied versions) — safe to call
    repeatedly. Returns the list of versions applied in this call."""
    from alpha_agent.storage.migrations.runner import apply_migrations

    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise HTTPException(500, "DATABASE_URL not set")
    applied = await apply_migrations(dsn)
    return {"applied": applied}


@router.post("/live-expression")
async def post_live_expression(
    request: Request,
    body: dict = Body(default_factory=dict),
    user_id: int = Depends(require_user),
    pool=Depends(get_db_pool),
) -> dict:
    """Manually set the live factor expression (admin gate).

    Validates the expression via factor_ast (same allow-lists as the
    proposer / backtester) and writes it via set_config. Returns the
    persisted expression + a timestamp.

    On invalid expression (unknown operator, unknown operand, syntax error)
    returns 400 with FastAPI's standard {detail: ...} envelope so the front
    end errorParse helper can surface the upstream message.
    """
    import ast as _ast
    from datetime import datetime, timezone

    from alpha_agent.core.factor_ast import (
        FactorSpecValidationError,
        validate_expression,
    )

    expression = str(body.get("expression", "")).strip()
    if not expression:
        raise HTTPException(400, "expression is required")

    # validate_expression requires declared_ops and cross-checks it against
    # used operators (the LLM-drift guard). For a manual admin entry there is
    # no upstream declaration to verify, so pre-walk the AST to derive the
    # actually-used operator set and pass that — the equality check then
    # passes trivially, and we still get the operator/operand/syntax allow-
    # list enforcement which is what we care about here.
    try:
        used_ops: set[str] = set()
        try:
            _tree = _ast.parse(expression, mode="eval")
        except SyntaxError as exc:
            raise FactorSpecValidationError(
                f"unparseable expression: {exc}"
            ) from exc
        for node in _ast.walk(_tree):
            if isinstance(node, _ast.Call) and isinstance(node.func, _ast.Name):
                used_ops.add(node.func.id)
        validate_expression(expression, used_ops)
    except FactorSpecValidationError as exc:
        raise HTTPException(400, f"spec invalid: {exc}") from exc

    # Persist via the same journaled write the approve handler uses. Key is
    # 'factor.custom_expression' to match the read path in signals/factor.py.
    await set_config(
        pool,
        "factor.custom_expression",
        expression,
        user_id=user_id,
        source="manual",
    )
    return {
        "expression": expression,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/_demo_seed")
async def post_demo_seed(
    user_id: int = Depends(require_user),
    pool=Depends(get_db_pool),
) -> dict:
    """Insert 3 demo pending proposals so PendingProposalsSection has visible
    rows for UX verification. Refuses to seed if any pending rows already
    exist — re-trigger only after the existing ones are approved/rejected.

    This is a temporary admin tool. Safe to call repeatedly: idempotent
    against existing pending state.
    """
    existing = await pool.fetchval(
        "SELECT count(*) FROM factor_proposals WHERE status='pending'"
    )
    if existing and existing > 0:
        raise HTTPException(
            400,
            f"refusing to seed: {existing} pending row(s) already exist; "
            "approve or reject them first",
        )

    # Read current diagnostic so each seeded row carries a realistic snapshot
    await refresh_config(pool)
    diag = await compute_diagnostic(pool)
    diag_jsonb = diag.to_jsonable()

    demos = [
        {
            "expression": "rank(ts_decay_linear(returns, 10))",
            "new_operators": [],
            "evidence": {
                "sharpes": [1.42, 1.31, 1.18],
                "ic_oos": 0.038,
                "deflated_sharpe": 0.62,
                "baseline_sharpe": 1.05,
                "n_folds": 3,
                "n_trials": 5,
                "llm_rationale": (
                    "Time-decay weighted recent returns capture short-horizon "
                    "momentum better than equal-weighted ts_mean. Linear decay "
                    "preserves recent signal without overfitting the tail."
                ),
                "operator_test_results": [],
            },
        },
        {
            "expression": "rank(divide(ts_mean(returns, 20), ts_std(volume, 20)))",
            "new_operators": [],
            "evidence": {
                "sharpes": [1.28, 1.55, 1.04],
                "ic_oos": 0.041,
                "deflated_sharpe": 0.18,
                "baseline_sharpe": 1.05,
                "n_folds": 3,
                "n_trials": 5,
                "llm_rationale": (
                    "Volatility-of-volume as a regime filter: high volume "
                    "dispersion suggests information arrival; dividing return "
                    "by volume std emphasizes returns earned under noisy tape."
                ),
                "operator_test_results": [],
            },
        },
        {
            "expression": "subtract(rank(ts_mean(returns, 12)), rank(lf_ts_skew(returns, 30)))",
            "new_operators": [
                {
                    "name": "lf_ts_skew",
                    "signature": "(x: np.ndarray, window: int) -> np.ndarray",
                    "python_impl": (
                        "def lf_ts_skew(x, window):\n"
                        "    import numpy as np\n"
                        "    out = np.full_like(x, np.nan, dtype=float)\n"
                        "    for i in range(window - 1, len(x)):\n"
                        "        sub = x[i - window + 1 : i + 1]\n"
                        "        m = np.nanmean(sub)\n"
                        "        s = np.nanstd(sub, ddof=1)\n"
                        "        if s > 1e-12:\n"
                        "            out[i] = np.nanmean(((sub - m) / s) ** 3)\n"
                        "    return out\n"
                    ),
                    "doc": "Rolling skewness of returns over `window` days.",
                }
            ],
            "evidence": {
                "sharpes": [0.98, 1.12, 1.21],
                "ic_oos": 0.029,
                "deflated_sharpe": -0.05,
                "baseline_sharpe": 1.05,
                "n_folds": 3,
                "n_trials": 5,
                "llm_rationale": (
                    "Negative skew penalty: stocks with rolling-skew-rich "
                    "return distributions tend to mean-revert. Pair with "
                    "ts_mean momentum to capture asymmetric reversal."
                ),
                "operator_test_results": [
                    {
                        "name": "lf_ts_skew",
                        "passed": True,
                        "n_tests": 4,
                        "n_passed": 4,
                    }
                ],
            },
        },
    ]

    inserted_ids = []
    for d in demos:
        row = await pool.fetchrow(
            "INSERT INTO factor_proposals "
            "(status, expression, new_operators, evidence, diagnostic) "
            "VALUES ('pending', $1, $2::jsonb, $3::jsonb, $4::jsonb) "
            "RETURNING id",
            d["expression"],
            json.dumps(d["new_operators"]),
            json.dumps(d["evidence"]),
            json.dumps(diag_jsonb),
        )
        inserted_ids.append(row["id"])

    return {
        "seeded": len(inserted_ids),
        "ids": inserted_ids,
        "note": "Refresh /factor-lab page to see them in PENDING PROPOSALS.",
    }


# ---------------------------------------------------------------------------
# Phase 3d: human-gated approval layer for factor proposals
# ---------------------------------------------------------------------------


def _decode_jsonb(value):
    """asyncpg may return jsonb as either a pre-decoded dict/list or a str
    depending on driver version. Normalize to native Python."""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return value
    return value


@router.get("/proposals")
async def list_proposals(
    status: str | None = None,
    pool=Depends(get_db_pool),
) -> dict:
    """List factor proposals. Optional ?status filter. Unauthed read (matches
    the existing /diagnostic and the Phase 2c evolution router precedent)."""
    if status is None:
        rows = await pool.fetch(
            "SELECT id, status, expression, new_operators, evidence, diagnostic, "
            "created_at, decided_at, decided_by FROM factor_proposals "
            "ORDER BY created_at DESC LIMIT 200"
        )
    else:
        if status not in {"pending", "approved", "rejected"}:
            raise HTTPException(400, f"invalid status: {status}")
        rows = await pool.fetch(
            "SELECT id, status, expression, new_operators, evidence, diagnostic, "
            "created_at, decided_at, decided_by FROM factor_proposals "
            "WHERE status = $1 ORDER BY created_at DESC LIMIT 200",
            status,
        )
    return {"proposals": [{
        "id": r["id"],
        "status": r["status"],
        "expression": r["expression"],
        "new_operators": _decode_jsonb(r["new_operators"]) or [],
        "evidence": _decode_jsonb(r["evidence"]) or {},
        "diagnostic": _decode_jsonb(r["diagnostic"]) or {},
        "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        "decided_at": r["decided_at"].isoformat() if r["decided_at"] else None,
        "decided_by": r["decided_by"],
    } for r in rows]}


@router.post("/proposals/{proposal_id}/approve")
async def approve_proposal(
    proposal_id: int,
    user_id: int = Depends(require_user),
    pool=Depends(get_db_pool),
) -> dict:
    """Approve a pending proposal:
      1. Register each new operator in extended_operators (ON CONFLICT DO NOTHING).
      2. set_config('factor.custom_expression', proposal.expression) via the
         shared journal (config_change_log gets a source='approved' row that
         the rollback handler later reads).
      3. UPDATE proposal status=approved + decided_at + decided_by.
      4. refresh_allowed_ops so the AST validator accepts the new operator
         names from the next request; failure surfaces in response.refresh_error
         (anti-silent: do not log + pretend success)."""
    row = await pool.fetchrow(
        "SELECT expression, new_operators FROM factor_proposals "
        "WHERE id=$1 AND status='pending'",
        proposal_id,
    )
    if row is None:
        raise HTTPException(404, "proposal not found or not pending")
    new_ops = _decode_jsonb(row["new_operators"]) or []
    for op in new_ops:
        await pool.execute(
            "INSERT INTO extended_operators "
            "(name, signature, python_impl, doc, registered_by, source_proposal_id) "
            "VALUES ($1, $2, $3, $4, $5, $6) "
            "ON CONFLICT (name) DO NOTHING",
            op["name"], op.get("signature", ""), op["python_impl"],
            op.get("doc", ""), user_id, proposal_id,
        )
    await set_config(pool, "factor.custom_expression",
                     row["expression"], user_id=user_id, source="approved")
    await pool.execute(
        "UPDATE factor_proposals SET status='approved', decided_at=now(), decided_by=$1 "
        "WHERE id=$2", user_id, proposal_id,
    )
    try:
        await refresh_allowed_ops(pool)
        refresh_error: str | None = None
    except Exception as exc:  # noqa: BLE001 - surfaced in response per anti-silent rule
        refresh_error = f"{type(exc).__name__}: {exc}"
    return {
        "ok": True,
        "applied": {"factor.custom_expression": row["expression"]},
        "registered_operators": [op["name"] for op in new_ops],
        "refresh_error": refresh_error,
    }


@router.post("/proposals/{proposal_id}/reject")
async def reject_proposal(
    proposal_id: int,
    user_id: int = Depends(require_user),
    pool=Depends(get_db_pool),
) -> dict:
    """Mark the proposal rejected. 404 on missing/decided rows (mirror the
    Phase 2b reject 404 symmetry fix; silent ok=true would be misleading)."""
    status = await pool.execute(
        "UPDATE factor_proposals SET status='rejected', decided_at=now(), decided_by=$1 "
        "WHERE id=$2 AND status='pending'", user_id, proposal_id,
    )
    if status.rsplit(" ", 1)[-1] == "0":
        raise HTTPException(404, "proposal not found or not pending")
    return {"ok": True}


@router.post("/proposals/{proposal_id}/rollback")
async def rollback_proposal(
    proposal_id: int,
    user_id: int = Depends(require_user),
    pool=Depends(get_db_pool),
) -> dict:
    """Revert factor.custom_expression to its pre-approval value, sourced from
    the config_change_log row that the approve handler wrote (source='approved',
    changed_at <= proposal.decided_at, most recent). Operators stay registered
    in extended_operators (audit + reproducibility, per the Phase 3 spec)."""
    row = await pool.fetchrow(
        "SELECT decided_at FROM factor_proposals "
        "WHERE id=$1 AND status='approved'", proposal_id,
    )
    if row is None:
        raise HTTPException(404, "approved proposal not found")
    prior = await pool.fetchrow(
        "SELECT old_value FROM config_change_log "
        "WHERE field='factor.custom_expression' AND source='approved' "
        "AND changed_at <= $1 ORDER BY changed_at DESC LIMIT 1",
        row["decided_at"],
    )
    old_value = _decode_jsonb(prior["old_value"]) if prior and prior["old_value"] else None
    await set_config(pool, "factor.custom_expression",
                     old_value, user_id=user_id, source="rollback")
    return {"ok": True, "reverted_to": old_value}
