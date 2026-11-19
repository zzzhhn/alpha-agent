"""Zoo cross-factor correlation endpoint (T2.1 of v4).

Why: a user saving 5 factors that turn out to be 0.95-correlated has 1 alpha,
not 5. The localStorage Zoo doesn't know which entries are near-duplicates.
This endpoint evaluates each saved FactorSpec on the active panel, builds the
daily long-short strategy return for each (top 30% long, bottom 30% short,
equal-weight), and computes the pairwise Pearson correlation matrix.

The daily-return correlation is the right answer here — it reflects what the
user would actually trade, not just whether two factor expressions agree on
ranks. Two factors with opposite signs but the same daily PnL sequence read
as +1 correlated, which is what we want for redundancy purposes.
"""
from __future__ import annotations

import logging

import numpy as np
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from alpha_agent.core.factor_ast import (
    FactorSpecValidationError as _FactorSpecValidationError,
)
from alpha_agent.core.factor_ast import validate_expression as _validate_expression
from alpha_agent.core.types import FactorSpec
from alpha_agent.factor_engine.portfolio import quantile_weights, realized_basket_returns

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/zoo", tags=["zoo"])


class _FactorEntry(BaseModel):
    spec: FactorSpec
    label: str | None = Field(
        default=None,
        description="Display name for this factor (defaults to spec.name).",
    )


class CorrelationRequest(BaseModel):
    factors: list[_FactorEntry] = Field(..., min_length=2, max_length=20)
    top_pct: float = Field(default=0.30, ge=0.01, le=0.50)
    bottom_pct: float = Field(default=0.30, ge=0.01, le=0.50)
    warn_threshold: float = Field(
        default=0.8, ge=0.5, le=0.99,
        description="A pair warns when its |correlation| meets or exceeds this value.",
    )


class _CorrWarning(BaseModel):
    a: str
    b: str
    corr: float


class CorrelationResponse(BaseModel):
    """Square matrix in `names` order; null means Pearson is undefined.

    A pair needs at least two shared observed returns and nonconstant returns
    for both factors. An available measured zero is always returned as 0.0.
    """
    names: list[str]
    matrix: list[list[float | None]]
    warnings: list[_CorrWarning]
    warn_threshold: float
    n_sessions: int  # number of trading days each factor's daily return spans


def _factor_daily_returns(
    factor: np.ndarray,
    fwd_returns: np.ndarray,
    top_pct: float,
    bottom_pct: float,
) -> np.ndarray:
    """Equal-weight long-short daily strategy return from factor + fwd-return.

    Same logic as factor_backtest.py's portfolio construction but stripped to
    just the daily PnL series — no metrics, no equity curve.
    """
    weights = quantile_weights(factor, top_pct, bottom_pct)
    return realized_basket_returns(weights, fwd_returns, require_exposure=True)


@router.post("/correlation", response_model=CorrelationResponse)
def run_zoo_correlation(body: CorrelationRequest) -> CorrelationResponse:
    """Pairwise correlation of daily long-short returns across saved factors.

    422 if any factor's expression is AST-invalid or fails to evaluate.
    503 if the panel parquet is missing.
    """
    try:
        from alpha_agent.factor_engine.factor_backtest import _load_panel
        from alpha_agent.factor_engine.kernel import evaluate_factor_full
        from alpha_agent.scan.significance import cross_correlation_matrix
    except ImportError as exc:
        raise HTTPException(
            503,
            f"factor_engine module failed to import: {type(exc).__name__}: {exc}",
        ) from exc

    try:
        panel = _load_panel()
    except FileNotFoundError as exc:
        raise HTTPException(503, f"Panel data missing: {exc}") from exc

    fwd_returns = np.full_like(panel.close, np.nan)
    fwd_returns[:-1] = panel.close[1:] / panel.close[:-1] - 1.0

    returns_by_label: dict[str, np.ndarray] = {}
    for idx, entry in enumerate(body.factors):
        label = entry.label or entry.spec.name or f"factor_{idx}"
        # Disambiguate collisions
        original = label
        suffix = 1
        while label in returns_by_label:
            suffix += 1
            label = f"{original} ({suffix})"

        try:
            _validate_expression(entry.spec.expression, entry.spec.operators_used)
        except _FactorSpecValidationError as exc:
            raise HTTPException(
                422, f"factor[{idx}] {label!r} AST invalid: {exc}"
            ) from exc

        try:
            factor_full = evaluate_factor_full(panel, entry.spec)
        except (ValueError, KeyError, NotImplementedError) as exc:
            raise HTTPException(
                422,
                f"factor[{idx}] {label!r} evaluation failed: {type(exc).__name__}: {exc}",
            ) from exc

        daily_ret = _factor_daily_returns(
            factor_full, fwd_returns, body.top_pct, body.bottom_pct,
        )
        returns_by_label[label] = daily_ret

    names, corr, warnings = cross_correlation_matrix(
        returns_by_label, warn_threshold=body.warn_threshold,
    )
    matrix_list = [[float(v) if np.isfinite(v) else None for v in row] for row in corr]

    return CorrelationResponse(
        names=names,
        matrix=matrix_list,
        warnings=[_CorrWarning(a=a, b=b, corr=c) for a, b, c in warnings],
        warn_threshold=body.warn_threshold,
        n_sessions=int(panel.close.shape[0]),
    )
