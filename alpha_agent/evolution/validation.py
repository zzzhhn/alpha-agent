"""Purged walk-forward + Deflated-Sharpe-lite (numpy only, no scipy/sklearn).

SLICE A: purged_fold_indices + deflated_sharpe_lite  -- pure math, no IO.
SLICE B: CandidateResult + evaluate_candidate        -- real DB + kernel.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from alpha_agent.evolution.candidates import ConfigDelta


# Minimum number of OOS folds required to consider the result meaningful.
# Fewer than 3 folds gives too little signal to trust any deflated Sharpe.
MIN_FOLDS = 3

# Minimum rows per fold for the kernel to compute a meaningful Sharpe
# (needs >1 clean day, but we want at least a few weeks of OOS data).
_MIN_ROWS_PER_FOLD = 15

# Forward horizon used by the IC engine (5 trading days). The embargo guard
# must be at least this large so OOS labels cannot bleed into training.
_EMBARGO = 5


def purged_fold_indices(n: int, n_folds: int, embargo: int) -> list[tuple[list[int], list[int]]]:
    """Contiguous-block walk-forward folds with a purge+embargo gap: each test
    block excludes `embargo` train days on both sides so a label that overlaps
    the test window cannot leak into training."""
    bounds = np.linspace(0, n, n_folds + 1).astype(int)
    folds = []
    for i in range(n_folds):
        lo, hi = bounds[i], bounds[i + 1] - 1
        test_idx = list(range(lo, hi + 1))
        train_idx = [t for t in range(n) if t < lo - embargo or t > hi + embargo]
        folds.append((train_idx, test_idx))
    return folds


def deflated_sharpe_lite(best_sharpe: float, sharpes: list[float], n_trials: int) -> float:
    """Discount the best observed Sharpe by the cross-trial spread times
    log(n_trials) (more trials -> more selection bias -> larger haircut). Lite
    proxy for the Deflated Sharpe Ratio."""
    arr = np.asarray(sharpes, dtype=float)
    spread = float(arr.std()) if len(arr) > 1 else 0.0
    haircut = spread * float(np.log1p(n_trials))
    return float(best_sharpe - haircut)


@dataclass(frozen=True)
class CandidateResult:
    delta: "ConfigDelta"    # from alpha_agent.evolution.candidates
    sharpes: list[float]    # OOS Sharpe per fold
    ic_oos: float           # mean OOS IC across folds
    n_folds: int


async def evaluate_candidate(pool, delta: "ConfigDelta", *, context=None) -> "CandidateResult | None":
    """Only factor.mode is represented by this kernel. Never mutate live config.

    Rating/IC thresholds do not change kernel holdings, so evaluating those
    deltas here would falsely claim evidence for an untested behavior.
    """
    import asyncio
    from alpha_agent.evolution.research_panel import (
        InvalidEvaluation, load_research_context, score_expression,
    )
    from alpha_agent.signals.factor import SHORT_TERM_FACTOR_EXPR, LONG_TERM_FACTOR_EXPR

    if delta.key != "factor.mode" or delta.new_value not in ("long", "short"):
        raise InvalidEvaluation("unsupported_config_delta", delta.key)
    context = context or await asyncio.to_thread(load_research_context)
    expression = LONG_TERM_FACTOR_EXPR if delta.new_value == "long" else SHORT_TERM_FACTOR_EXPR
    try:
        sharpes, ic, _ = await asyncio.to_thread(score_expression, context, expression)
    except InvalidEvaluation:
        return None
    return CandidateResult(delta=delta, sharpes=sharpes, ic_oos=ic, n_folds=len(sharpes))
