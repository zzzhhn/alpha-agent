"""Phase 3c factor candidate validator.

Reuses Phase 2a's purged_fold_indices + the same daily_prices read path.
New: routes proposal's lf_* operators through SandboxRunner via the kernel's
extra_ops plumbing (T4 changes to scan/vectorized + kernel.py).

Returns None when usable history yields fewer than MIN_FOLDS folds, OR when
any new operator fails canned tests.

Panel-load + fold loop ported from alpha_agent/evolution/validation.py
evaluate_candidate (lines 83-273, Phase 2a implementation).
"""
from __future__ import annotations

import ast
import sys
from dataclasses import dataclass

from alpha_agent.evolution.llm_factor_proposer import RawProposal
from alpha_agent.evolution.sandbox import (
    SandboxError,
    SandboxRunner,
    run_canned_tests,
)
from alpha_agent.evolution.validation import (
    MIN_FOLDS as MIN_FOLDS,
)


def _emit_reject(
    expr: str,
    reason: str,
    *,
    out_rejects: list | None = None,
    **detail,
) -> None:
    """Surface candidate-rejection reason both to stderr (Vercel CLI logs)
    AND to an optional in-memory collector so the API handler can return the
    reason in the response body. stderr-only emit was insufficient because
    Vercel CLI captured only the first stderr line per lambda invocation,
    leaving 0/N propose outcomes opaque from the frontend."""
    detail_str = " ".join(f"{k}={v!r}" for k, v in detail.items())
    try:
        print(
            f"[evaluate_factor_candidate] REJECT expr={expr[:120]!r} "
            f"reason={reason} {detail_str}",
            file=sys.stderr,
            flush=True,
        )
    except Exception:  # noqa: BLE001 - logger must never block recovery path
        pass
    if out_rejects is not None:
        try:
            out_rejects.append({
                "expression": expr[:120],
                "reason": reason,
                "detail": {k: repr(v)[:200] for k, v in detail.items()},
            })
        except Exception:  # noqa: BLE001 - collector must not block recovery
            pass

_EMBARGO = 5       # must be >= forward horizon (_FWD_RET_DAYS in ic_engine)
_N_FOLDS = 3       # matches MIN_FOLDS
_MIN_ROWS_PER_FOLD = 15


@dataclass(frozen=True)
class FactorCandidateResult:
    expression: str
    new_operators: list[dict]
    sharpes: list[float]
    ic_oos: float
    n_folds: int
    operator_test_results: list[dict]


def _extract_arg_names(op_code: str, op_name: str) -> list[str]:
    """Parse the LLM-supplied python_impl to extract the function's positional
    parameter names. The DSL invokes the op positionally; the worker calls
    fn(**args) by name. We bind positionals to names by parsing the source."""
    tree = ast.parse(op_code)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == op_name:
            return [a.arg for a in node.args.args]
    raise ValueError(f"function {op_name!r} not found in python_impl")


def _build_sandbox_dispatch(runner: SandboxRunner, ops: list[dict]) -> dict:
    """Build extra_ops dict for the kernel chain. Each entry is a closure that
    binds positional args (from the DSL invocation) to the LLM function's
    parameter names, then routes via SandboxRunner.

    SandboxError is turned into RuntimeError so the fold loop can treat it as
    a degraded fold (catches Exception, records zero Sharpe/IC and continues).
    """
    dispatch: dict = {}
    for op in ops:
        name = op["name"]
        code = op["python_impl"]
        arg_names = _extract_arg_names(code, name)

        def _make(op_name: str = name, op_code: str = code, names: list[str] = arg_names):
            def _fn(*positional):
                if len(positional) > len(names):
                    raise RuntimeError(
                        f"{op_name}: too many args ({len(positional)} > {len(names)})"
                    )
                bound: dict = {}
                for i, val in enumerate(positional):
                    bound[names[i]] = val
                out = runner.evaluate(op_code=op_code, op_name=op_name, args=bound)
                if isinstance(out, SandboxError):
                    raise RuntimeError(
                        f"sandbox {out.kind.value}: {out.detail[:200]}"
                    )
                return out
            return _fn

        dispatch[name] = _make()
    return dispatch


async def evaluate_factor_candidate(
    pool,
    runner: SandboxRunner,
    proposal: RawProposal,
    out_rejects: list | None = None,
    *,
    context=None,
) -> FactorCandidateResult | None:
    """Validate against one real chronological panel; invalid is never zero."""
    import asyncio
    from alpha_agent.evolution.research_panel import (
        InvalidEvaluation, load_research_context, score_expression,
    )

    op_test_results = []
    for op in proposal.new_operators:
        result = run_canned_tests(runner, op_code=op["python_impl"], op_name=op["name"],
                                 signature=op.get("signature", "(x: ndarray) -> ndarray"))
        op_test_results.append({"name": op["name"], "passed": result.passed, "tests": result.tests})
        if not result.passed:
            _emit_reject(proposal.expression, "canned_test_failed",
                         out_rejects=out_rejects, op_name=op["name"])
            return None
    try:
        context = context or await asyncio.to_thread(load_research_context)
        extra_ops = _build_sandbox_dispatch(runner, proposal.new_operators)
        sharpes, ic, _ = await asyncio.to_thread(
            score_expression, context, proposal.expression, extra_ops=extra_ops)
    except InvalidEvaluation as exc:
        _emit_reject(proposal.expression, exc.reason, out_rejects=out_rejects,
                     status="invalid_evaluation", detail=str(exc))
        return None
    except Exception as exc:
        _emit_reject(proposal.expression, "evaluation_exception", out_rejects=out_rejects,
                     status="invalid_evaluation", detail=f"{type(exc).__name__}: {exc}")
        return None
    return FactorCandidateResult(expression=proposal.expression,
                                 new_operators=list(proposal.new_operators),
                                 sharpes=sharpes, ic_oos=ic, n_folds=len(sharpes),
                                 operator_test_results=op_test_results)
