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

import asyncio
import json

from fastapi import APIRouter, Body, Depends, HTTPException, Request

from alpha_agent.api.byok import get_llm_client
from alpha_agent.api.dependencies import get_db_pool
from alpha_agent.auth.dependencies import require_user
from alpha_agent.config_store import refresh_config, set_config
from alpha_agent.core.factor_ast import refresh_allowed_ops
from alpha_agent.evolution.diagnostics import compute_diagnostic
from alpha_agent.evolution.factor_validation import evaluate_factor_candidate
from alpha_agent.evolution.llm_factor_proposer import RawProposal, propose_factors
from alpha_agent.evolution.sandbox import SandboxRunner
from alpha_agent.evolution.validation import deflated_sharpe_lite

router = APIRouter(prefix="/api/factor-lab", tags=["factor_lab"])

# Cost-guard threshold: roughly 3 folds * 30 test days * 10 tickers = 900 rows.
# Below this, the validator cannot produce MIN_FOLDS folds, so the LLM call
# would be wasted; return dormant immediately.
_MIN_HISTORY_ROWS = 1000

# Relaxed thresholds (2026-05-25): previously both r_mean > base_mean AND
# defl > 0 were hard gates; that filtered 100% of Kimi's proposals every
# run. User decision: keep a filter but loosen so marginal candidates
# reach human review. Human is the final gate; surfacing more candidates
# surfaces more learning even if approval rate drops.
_BASE_RATIO = 0.9           # accept r_mean as low as 90% of baseline Sharpe
_DSR_THRESHOLD = -0.5       # accept deflated Sharpe down to -0.5


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


@router.post("/propose")
async def post_propose(
    request: Request,
    body: dict = Body(default_factory=dict),
    user_id: int = Depends(require_user),
    pool=Depends(get_db_pool),
) -> dict:
    """Run the propose loop. Returns {evaluated, proposed, dormant}.
    Dormant=True means cost-guard or validator-dormant; LLM is NOT called
    when cost-guard fires.

    get_llm_client is resolved lazily AFTER the cost-guard check so that
    thin-history deploys never waste a BYOK round-trip."""
    import numpy as np

    n = int(body.get("n", 5)) if isinstance(body, dict) else 5

    # Same cache-refresh rationale as get_diagnostic: propose builds its
    # baseline from compute_diagnostic().current_expression, which routes
    # through the process-cache. Without this refresh, a manual edit from
    # another lambda instance is invisible here and the LLM is asked to
    # beat the stale preset instead of the user's intended baseline.
    await refresh_config(pool)

    # Cost-guard: skip LLM if history is too thin to validate anything.
    # This fires BEFORE the BYOK dependency so no LLM call is wasted.
    history_n = await pool.fetchval("SELECT count(*) FROM daily_prices") or 0
    if history_n < _MIN_HISTORY_ROWS:
        return {"evaluated": 0, "proposed": 0, "dormant": True}

    # Lazy BYOK: only resolve after cost-guard passes.
    llm_client = await get_llm_client(user_id=user_id)

    diagnostic = await compute_diagnostic(pool)

    try:
        raw_proposals = await propose_factors(llm_client, diagnostic, n=n)
    except asyncio.TimeoutError as exc:
        # propose_factors uses asyncio.wait_for(timeout=_WALL_CLOCK_S=240s).
        # Surface as a clean 504 so the client gets an actionable error message
        # instead of an opaque 500 with empty body (CLAUDE.md silent-exception
        # anti-pattern). Wall-clock exceeded usually means Kimi-for-Coding
        # response stream slow or model overloaded; smaller n or a retry
        # typically clears it.
        raise HTTPException(
            status_code=504,
            detail=f"LLM proposer timed out after wall clock; retry or reduce n",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"LLM proposer: {exc}",
        ) from exc
    if not raw_proposals:
        return {"evaluated": 0, "proposed": 0, "dormant": False}

    runner = SandboxRunner()
    try:
        # 1. Evaluate each candidate (canned tests + purged WF)
        results = []
        for proposal in raw_proposals:
            r = await evaluate_factor_candidate(pool, runner, proposal)
            if r is not None:
                results.append(r)
        if not results:
            return {"evaluated": len(raw_proposals), "proposed": 0, "dormant": False}

        # 2. Baseline: re-evaluate current expression for comparison.
        baseline = await evaluate_factor_candidate(
            pool, runner,
            RawProposal(expression=diagnostic.current_expression, new_operators=[]),
        )
        if baseline is None:
            return {"evaluated": len(raw_proposals), "proposed": 0, "dormant": True}

        # 3. DSR-lite deflation: keep only survivors that beat baseline AND
        #    have post-deflation positive Sharpe.
        import sys as _sys
        all_means = [float(np.mean(r.sharpes)) for r in results]
        base_mean = float(np.mean(baseline.sharpes))
        # Emit the baseline + thresholds once per propose call so the
        # per-candidate decisions below are interpretable against the same
        # frame of reference.
        print(
            f"[propose:DSR] base_mean={base_mean:.4f} "
            f"base_threshold={base_mean * _BASE_RATIO:.4f} "
            f"defl_threshold={_DSR_THRESHOLD:.4f} "
            f"n_candidates={len(results)}",
            file=_sys.stderr, flush=True,
        )
        proposed_count = 0
        for r in sorted(results, key=lambda r: -float(np.mean(r.sharpes))):
            r_mean = float(np.mean(r.sharpes))
            defl = deflated_sharpe_lite(r_mean, all_means, len(raw_proposals))
            passes_mean = r_mean > base_mean * _BASE_RATIO
            passes_defl = defl > _DSR_THRESHOLD
            print(
                f"[propose:DSR] expr={r.expression[:80]!r} "
                f"r_mean={r_mean:.4f} defl={defl:.4f} "
                f"passes_mean={passes_mean} passes_defl={passes_defl}",
                file=_sys.stderr, flush=True,
            )
            if passes_mean and passes_defl:
                rationale = next(
                    (p.rationale for p in raw_proposals if p.expression == r.expression),
                    "",
                )
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
                    }),
                    json.dumps(diagnostic.to_jsonable()),
                )
                proposed_count += 1

        return {
            "evaluated": len(raw_proposals),
            "proposed": proposed_count,
            "dormant": False,
        }
    finally:
        runner.close()


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
