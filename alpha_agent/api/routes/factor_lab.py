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

from fastapi import APIRouter, Body, Depends, HTTPException, Request

from alpha_agent.api.byok import get_llm_client
from alpha_agent.api.dependencies import get_db_pool
from alpha_agent.auth.dependencies import require_user
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


@router.get("/diagnostic")
async def get_diagnostic(pool=Depends(get_db_pool)) -> dict:
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
        all_means = [float(np.mean(r.sharpes)) for r in results]
        base_mean = float(np.mean(baseline.sharpes))
        proposed_count = 0
        for r in sorted(results, key=lambda r: -float(np.mean(r.sharpes))):
            r_mean = float(np.mean(r.sharpes))
            defl = deflated_sharpe_lite(r_mean, all_means, len(raw_proposals))
            if r_mean > base_mean and defl > 0:
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
