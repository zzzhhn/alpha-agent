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
from dataclasses import dataclass

import numpy as np

from alpha_agent.evolution.llm_factor_proposer import RawProposal
from alpha_agent.evolution.sandbox import (
    CannedTestResult,
    SandboxError,
    SandboxRunner,
    run_canned_tests,
)
from alpha_agent.evolution.validation import (
    MIN_FOLDS,
    purged_fold_indices,
)

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
) -> FactorCandidateResult | None:
    """Run canned tests on every new operator (reject candidate on any fail),
    then purged WF OOS folds with sandbox-dispatched new ops.

    Returns None on dormant-when-starved OR any canned-test failure.

    Panel-load + fold loop mirrors alpha_agent/evolution/validation.py
    evaluate_candidate lines 83-273 exactly, replacing the _CACHE delta
    override with extra_ops=extra_ops passed to run_kernel.
    """
    from alpha_agent.core.types import FactorSpec
    from alpha_agent.factor_engine.factor_backtest import _Panel
    from alpha_agent.factor_engine.kernel import KernelParams, run_kernel, spearman_ic

    # ------------------------------------------------------------------ #
    # 1. Canned tests on every new operator (fast rejection path)
    # ------------------------------------------------------------------ #
    op_test_results: list[dict] = []
    for op in proposal.new_operators:
        result: CannedTestResult = run_canned_tests(
            runner,
            op_code=op["python_impl"],
            op_name=op["name"],
            signature=op.get("signature", "(x: ndarray) -> ndarray"),
        )
        op_test_results.append({
            "name": op["name"],
            "passed": result.passed,
            "tests": result.tests,
        })
        if not result.passed:
            return None  # reject candidate immediately; any canned-test failure disqualifies

    extra_ops = _build_sandbox_dispatch(runner, proposal.new_operators)

    # ------------------------------------------------------------------ #
    # 2. Load close history from daily_prices (mirrors validation.py:95-124)
    # ------------------------------------------------------------------ #
    rows = await pool.fetch(
        "SELECT ticker, date, close FROM daily_prices ORDER BY date, ticker"
    )
    if not rows:
        return None

    tickers_set: list[str] = sorted({r["ticker"] for r in rows})
    dates_set: list[str] = sorted({str(r["date"]) for r in rows})
    N = len(tickers_set)
    T = len(dates_set)

    ticker_idx = {t: i for i, t in enumerate(tickers_set)}
    date_idx = {d: i for i, d in enumerate(dates_set)}

    close_arr = np.full((T, N), np.nan)
    for r in rows:
        ti = ticker_idx[r["ticker"]]
        di = date_idx[str(r["date"])]
        close_arr[di, ti] = float(r["close"])

    # Drop tickers with all-NaN close
    valid_cols = ~np.all(np.isnan(close_arr), axis=0)
    close_arr = close_arr[:, valid_cols]
    tickers_arr = [t for t, v in zip(tickers_set, valid_cols) if v]
    N = close_arr.shape[1]

    if N < 10:
        return None

    # ------------------------------------------------------------------ #
    # 3. Decide fold geometry; return None when history is too short
    #    (mirrors validation.py:128-145)
    # ------------------------------------------------------------------ #
    n_folds = MIN_FOLDS
    if T // n_folds < _MIN_ROWS_PER_FOLD:
        return None

    folds = purged_fold_indices(n=T, n_folds=n_folds, embargo=_EMBARGO)

    usable_folds = [
        (train_idx, test_idx)
        for train_idx, test_idx in folds
        if len(test_idx) >= _MIN_ROWS_PER_FOLD and len(train_idx) >= _MIN_ROWS_PER_FOLD
    ]

    if len(usable_folds) < MIN_FOLDS:
        return None

    # ------------------------------------------------------------------ #
    # 4. Build FactorSpec from the proposal expression
    # ------------------------------------------------------------------ #
    spec = FactorSpec(
        name="factor_candidate",
        hypothesis="Phase 3c candidate evaluation",
        expression=proposal.expression,
        operators_used=[],
        lookback=60,
        universe="SP500",
        justification="Automated LLM factor proposal OOS evaluation.",
    )

    params = KernelParams(direction="long_short", n_trials=1)

    # ------------------------------------------------------------------ #
    # 5. Score each fold (mirrors validation.py:180-256)
    # ------------------------------------------------------------------ #
    fold_sharpes: list[float] = []
    fold_ics: list[float] = []

    rng = np.random.default_rng(seed=0)

    for train_idx, test_idx in usable_folds:
        # Stack train rows first, then test rows, so the kernel's train_ratio
        # boundary lands exactly on the train/test seam (see validation.py:194).
        sub_close = np.vstack([close_arr[train_idx, :], close_arr[test_idx, :]])
        sub_T = sub_close.shape[0]

        sub_open = sub_close * (1.0 + rng.normal(0.0, 0.001, size=sub_close.shape))
        sub_high = np.maximum(sub_open, sub_close) * 1.001
        sub_low = np.minimum(sub_open, sub_close) * 0.999
        sub_vol = np.full(sub_close.shape, 1_000_000.0)
        sub_dates = np.array(
            [f"2024-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}" for i in range(sub_T)]
        )
        sub_tickers = tuple(tickers_arr)
        bench = np.cumprod(1.0 + rng.normal(0.0003, 0.005, size=sub_T)) * 100.0

        panel = _Panel(
            dates=sub_dates,
            tickers=sub_tickers,
            close=sub_close,
            open_=sub_open,
            high=sub_high,
            low=sub_low,
            volume=sub_vol,
            benchmark_close=bench,
        )

        n_train = len(train_idx)
        n_test = len(test_idx)
        train_ratio = float(n_train) / float(n_train + n_test)

        fold_params = KernelParams(
            direction=params.direction,
            top_pct=params.top_pct,
            bottom_pct=params.bottom_pct,
            train_ratio=train_ratio,
            n_trials=params.n_trials,
        )

        try:
            kr = run_kernel(panel, spec, fold_params, extra_ops=extra_ops)
        except Exception:
            # A single fold failure (degenerate matrix, sandbox error, etc.)
            # must not abort the whole evaluation. Surface as zero metrics so
            # the deflated Sharpe reflects the degraded evidence.
            # (mirrors validation.py:239-245)
            fold_sharpes.append(0.0)
            fold_ics.append(0.0)
            continue

        fold_sharpes.append(float(kr.test_metrics.sharpe))

        # OOS IC: mean Spearman IC over the test slice rows
        # (mirrors validation.py:249-256)
        test_start = kr.train_end
        ic_vals: list[float] = []
        for t in range(test_start, sub_T):
            ic = spearman_ic(kr.factor[t], kr.fwd_returns[t])
            if not np.isnan(ic):
                ic_vals.append(ic)
        fold_ics.append(float(np.mean(ic_vals)) if ic_vals else 0.0)

    if len(fold_sharpes) < MIN_FOLDS:
        return None

    return FactorCandidateResult(
        expression=proposal.expression,
        new_operators=list(proposal.new_operators),
        sharpes=fold_sharpes,
        ic_oos=float(np.mean(fold_ics)),
        n_folds=len(fold_sharpes),
        operator_test_results=op_test_results,
    )
