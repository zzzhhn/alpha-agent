"""Multi-factor screener endpoint (D1 of v3).

Given a list of FactorSpecs (typically pulled from the user's Factor Zoo),
evaluates each at a chosen as-of date, optionally filters the universe by
sector / cap, z-scores each factor's cross-section, combines them via one
of three methods (equal-z / ic-weighted / user-weighted), and returns the
top-N tickers ranked by composite score.

Why the user wanted this (痛点 3 from v3 plan):
  Until now alpha-agent could backtest *one* factor at a time. There was
  no surface that says "given my Zoo of 5 factors, which 20 stocks should
  I pay attention to today?" — that's the missing last mile from research
  to decision.

Failure surfacing follows the same convention as `interactive.py`:
  422 → bad input (AST violation, unknown sector, empty result set)
  503 → panel missing (deploy-time data not committed)
  500 → evaluation crash (real bug, surface the type/message)

This endpoint is *upstream* of any persistent storage — recommendations are
not saved server-side. The frontend snapshots them to localStorage if the
user wants to keep one.
"""
from __future__ import annotations

import logging
from typing import Literal

import numpy as np
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from alpha_agent.core.factor_ast import (
    FactorSpecValidationError as _FactorSpecValidationError,
)
from alpha_agent.core.factor_ast import validate_expression as _validate_expression
from alpha_agent.core.types import FactorSpec

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/screener", tags=["screener"])


# ── Request / Response models ───────────────────────────────────────────────


class ScreenerFactor(BaseModel):
    """One factor to include in the composite. `weight` only matters when
    `combine_method == "user_weighted"`; ignored otherwise."""
    spec: FactorSpec
    direction: Literal["long_short", "long_only", "short_only"] = "long_short"
    weight: float = Field(default=1.0, ge=0.0, le=10.0)


class UniverseFilter(BaseModel):
    sectors: list[str] | None = Field(
        default=None,
        description="If set, keep only tickers whose sector is in this list.",
    )
    min_cap: float | None = Field(default=None, ge=0.0)
    max_cap: float | None = Field(default=None, ge=0.0)
    exclude_tickers: list[str] | None = None


class ScreenerRequest(BaseModel):
    factors: list[ScreenerFactor] = Field(..., min_length=1, max_length=10)
    universe_filter: UniverseFilter = Field(default_factory=UniverseFilter)
    lookback_days: int = Field(default=60, ge=10, le=252)
    top_n: int = Field(default=20, ge=1, le=100)
    combine_method: Literal["equal_z", "ic_weighted", "user_weighted"] = "equal_z"
    as_of_date: str | None = Field(
        default=None,
        description="YYYY-MM-DD; null = panel's most recent session.",
    )


class PerFactorScore(BaseModel):
    factor_idx: int
    raw: float
    z: float
    contribution: float  # signed contribution to composite


class Recommendation(BaseModel):
    ticker: str
    composite_score: float
    rank: int                                # 1-based
    sector: str | None = None
    cap: float | None = None
    per_factor_scores: list[PerFactorScore]


class FactorDiagnostic(BaseModel):
    factor_idx: int
    expression: str
    in_window_ic: float                # mean Spearman IC over the lookback window
    used_weight: float                 # actual weight applied in the combine step
    n_eligible: int                    # tickers with non-NaN score after universe filter


class ScreenerResponse(BaseModel):
    recommendations: list[Recommendation]
    factor_diagnostics: list[FactorDiagnostic]
    metadata: dict


# ── Helpers ─────────────────────────────────────────────────────────────────


def _z_score(values: np.ndarray) -> np.ndarray:
    """Cross-sectional z-score, NaN-safe. Returns same shape; NaN preserved."""
    mask = ~np.isnan(values)
    if int(mask.sum()) < 2:
        return np.full_like(values, np.nan, dtype=np.float64)
    valid = values[mask]
    mean = float(valid.mean())
    std = float(valid.std(ddof=1))
    z = np.full_like(values, np.nan, dtype=np.float64)
    if std > 0:
        z[mask] = (valid - mean) / std
    else:
        z[mask] = 0.0  # constant column → zero z-score, not NaN
    return z


def _resolve_as_of_index(panel_dates: np.ndarray, as_of_date: str | None) -> int:
    """Map an as-of-date string to a row index. Defaults to most recent."""
    if as_of_date is None:
        return int(len(panel_dates) - 1)
    target = str(as_of_date)
    matches = [i for i, d in enumerate(panel_dates) if str(d) == target]
    if not matches:
        raise HTTPException(
            422,
            f"as_of_date {target!r} not in panel "
            f"(range: {panel_dates[0]} → {panel_dates[-1]})",
        )
    return int(matches[0])


def _apply_universe_filter(
    panel,
    as_of_index: int,
    flt: UniverseFilter,
) -> np.ndarray:
    """Return a (N,) boolean mask over panel.tickers — True = keep."""
    n = len(panel.tickers)
    keep = np.ones(n, dtype=bool)

    if flt.exclude_tickers:
        excl = set(flt.exclude_tickers)
        keep &= np.array([tk not in excl for tk in panel.tickers], dtype=bool)

    if flt.sectors and panel.sector is not None:
        # Case-insensitive match to forgive "tech" vs "Technology" typos. The
        # original strings live in panel.sector verbatim, so lowercase both sides.
        wanted = {s.strip().lower() for s in flt.sectors}
        sector_row = panel.sector[as_of_index]
        keep &= np.array(
            [str(s).strip().lower() in wanted for s in sector_row],
            dtype=bool,
        )

    if (flt.min_cap is not None or flt.max_cap is not None) and panel.cap is not None:
        cap_row = panel.cap[as_of_index]
        if flt.min_cap is not None:
            keep &= ~np.isnan(cap_row) & (cap_row >= flt.min_cap)
        if flt.max_cap is not None:
            keep &= ~np.isnan(cap_row) & (cap_row <= flt.max_cap)

    return keep


# ── Endpoint ────────────────────────────────────────────────────────────────


@router.post("/run", response_model=ScreenerResponse)
def run_screener(body: ScreenerRequest) -> ScreenerResponse:
    """Evaluate factors → filter universe → z-score → combine → rank.

    Direction handling per factor:
      long_only / long_short → use raw (higher = better)
      short_only             → invert score (lower = better)

    Combine methods:
      equal_z         → mean of z-scores across factors
      ic_weighted     → weight each z-score by its in-window mean IC (clipped ≥ 0)
      user_weighted   → use per-factor weights from the request (normalized to sum=1)
    """
    # Lazy import: keeps the rest of the API alive if factor_engine breaks.
    try:
        from alpha_agent.factor_engine.factor_backtest import _load_panel
        from alpha_agent.factor_engine.kernel import (
            evaluate_factor_full,
            window_ic,
        )
    except ImportError as exc:
        raise HTTPException(
            503,
            f"factor_engine module failed to import: {type(exc).__name__}: {exc}",
        ) from exc

    try:
        panel = _load_panel()
    except FileNotFoundError as exc:
        raise HTTPException(503, f"Panel data missing: {exc}") from exc

    T, N = panel.close.shape
    as_of_idx = _resolve_as_of_index(panel.dates, body.as_of_date)
    keep_mask = _apply_universe_filter(panel, as_of_idx, body.universe_filter)
    if not keep_mask.any():
        # Self-diagnosing 422: tell the client what the panel actually contains
        # so they can correct the request without a second round-trip. Most
        # common cause is a sector name typo (case insensitive matching is
        # already done; this catches user typing a sector that simply doesn't
        # exist in the panel).
        diag: dict[str, object] = {}
        if body.universe_filter.sectors and panel.sector is not None:
            available = sorted({str(s) for s in panel.sector[as_of_idx]})
            diag["available_sectors"] = available
            diag["requested_sectors"] = list(body.universe_filter.sectors)
        if (
            (body.universe_filter.min_cap is not None or body.universe_filter.max_cap is not None)
            and panel.cap is not None
        ):
            cap_row = panel.cap[as_of_idx]
            cap_clean = cap_row[~np.isnan(cap_row)]
            if cap_clean.size > 0:
                diag["panel_cap_min"] = float(cap_clean.min())
                diag["panel_cap_max"] = float(cap_clean.max())
        raise HTTPException(
            422,
            f"universe_filter eliminated all tickers · diagnostic: {diag}",
        )

    # 1-day forward returns, used for IC weighting
    fwd_returns = np.full_like(panel.close, np.nan)
    fwd_returns[:-1] = panel.close[1:] / panel.close[:-1] - 1.0

    # Evaluate each factor and capture diagnostics + z-scored cross-section
    z_matrix: list[np.ndarray] = []          # one (N,) array per factor (NaN where filtered out)
    raw_matrix: list[np.ndarray] = []        # raw factor values at as_of_idx
    diagnostics: list[FactorDiagnostic] = []
    weights_used: list[float] = []

    for idx, f in enumerate(body.factors):
        try:
            _validate_expression(f.spec.expression, f.spec.operators_used)
        except _FactorSpecValidationError as exc:
            raise HTTPException(
                422, f"factor[{idx}] AST invalid: {exc}"
            ) from exc

        try:
            factor_full = evaluate_factor_full(panel, f.spec)
        except (ValueError, KeyError, NotImplementedError) as exc:
            raise HTTPException(
                422, f"factor[{idx}] evaluation failed: {type(exc).__name__}: {exc}"
            ) from exc

        row_raw = factor_full[as_of_idx].copy()
        # Direction: short_only → invert, others use raw
        if f.direction == "short_only":
            row_raw = -row_raw

        # Mask out filtered tickers BEFORE z-scoring — otherwise an excluded
        # outlier inflates the std and crushes everyone else's z.
        row_raw[~keep_mask] = np.nan
        row_z = _z_score(row_raw)

        # IC over the lookback window for diagnostics (and ic_weighted mode)
        ic_start = max(0, as_of_idx - body.lookback_days)
        ic_mean = window_ic(factor_full, fwd_returns, ic_start, as_of_idx)

        z_matrix.append(row_z)
        raw_matrix.append(row_raw)
        diagnostics.append(FactorDiagnostic(
            factor_idx=idx,
            expression=f.spec.expression,
            in_window_ic=ic_mean,
            used_weight=0.0,         # filled below after weight resolution
            n_eligible=int(np.sum(~np.isnan(row_z))),
        ))

    # Resolve per-factor weights based on combine_method
    n_f = len(body.factors)
    if body.combine_method == "equal_z":
        weights_used = [1.0 / n_f] * n_f
    elif body.combine_method == "user_weighted":
        total = sum(f.weight for f in body.factors)
        weights_used = (
            [f.weight / total for f in body.factors] if total > 0
            else [1.0 / n_f] * n_f
        )
    else:  # ic_weighted
        # Clip negative IC to 0 (negatively-correlated factors don't get
        # short-circuited into the long composite — they'd add noise). If all
        # IC ≤ 0, fall back to equal weighting so at least we return *something*.
        clipped = [max(0.0, d.in_window_ic) for d in diagnostics]
        total = sum(clipped)
        weights_used = (
            [c / total for c in clipped] if total > 0
            else [1.0 / n_f] * n_f
        )
    for d, w in zip(diagnostics, weights_used):
        d.used_weight = float(w)

    # Composite = weighted sum of z-scores. NaN propagates (any missing
    # factor → ticker dropped from ranking).
    composite = np.zeros(N, dtype=np.float64)
    for w, z in zip(weights_used, z_matrix):
        composite += w * np.nan_to_num(z, nan=0.0)
    # Mark tickers as ineligible if EVERY factor was NaN for them
    all_nan_mask = np.all(np.isnan(np.stack(z_matrix, axis=0)), axis=0)
    composite_masked = composite.copy()
    composite_masked[all_nan_mask | ~keep_mask] = np.nan

    # Top N by composite, descending; drop NaN
    valid_indices = np.where(~np.isnan(composite_masked))[0]
    sorted_indices = valid_indices[np.argsort(-composite_masked[valid_indices])]
    top = sorted_indices[: body.top_n]

    sector_row = panel.sector[as_of_idx] if panel.sector is not None else None
    cap_row = panel.cap[as_of_idx] if panel.cap is not None else None

    recs: list[Recommendation] = []
    for rank, i in enumerate(top, start=1):
        per_factor: list[PerFactorScore] = []
        for f_idx in range(n_f):
            z_val = z_matrix[f_idx][i]
            raw_val = raw_matrix[f_idx][i]
            contribution = (
                weights_used[f_idx] * (0.0 if np.isnan(z_val) else float(z_val))
            )
            per_factor.append(PerFactorScore(
                factor_idx=f_idx,
                raw=float(raw_val) if not np.isnan(raw_val) else 0.0,
                z=float(z_val) if not np.isnan(z_val) else 0.0,
                contribution=float(contribution),
            ))
        recs.append(Recommendation(
            ticker=str(panel.tickers[i]),
            composite_score=float(composite_masked[i]),
            rank=rank,
            sector=str(sector_row[i]) if sector_row is not None else None,
            cap=(
                float(cap_row[i]) if cap_row is not None and not np.isnan(cap_row[i])
                else None
            ),
            per_factor_scores=per_factor,
        ))

    return ScreenerResponse(
        recommendations=recs,
        factor_diagnostics=diagnostics,
        metadata={
            "as_of_date": str(panel.dates[as_of_idx]),
            "n_eligible_tickers": int(keep_mask.sum()),
            "method": body.combine_method,
            "lookback_days": body.lookback_days,
        },
    )
