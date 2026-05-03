"""Factor Performance DB endpoints (T4.1).

Replaces the localStorage-only Zoo with a server-backed registry. Every
backtest auto-saves via factor_backtest.run_factor_backtest's tail
hook; these endpoints expose read + decay-alert queries to the frontend.

Endpoints:
    GET    /api/v1/factors                  list saved factors (newest first)
    GET    /api/v1/factors/{factor_id}      detail + run history
    DELETE /api/v1/factors/{factor_id}      remove (cascades to runs)
    GET    /api/v1/factors/decay_alerts     factors whose recent IC dropped vs baseline
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from alpha_agent.storage import (
    decay_alerts as _decay_alerts,
    delete_factor as _delete_factor,
    get_factor_runs as _get_factor_runs,
    init_schema,
    list_factors as _list_factors,
)

router = APIRouter(prefix="/api/v1/factors", tags=["factors"])


try:
    init_schema()
except Exception as exc:  # noqa: BLE001
    import logging
    logging.getLogger(__name__).warning(
        "factor DB schema init failed: %s: %s — list endpoints will return empty",
        type(exc).__name__, exc,
    )


class FactorSummary(BaseModel):
    id: str
    ast_hash: str
    name: str
    expression: str
    hypothesis: str | None = None
    intuition: str | None = None
    last_direction: str | None = None
    last_neutralize: str | None = None
    last_benchmark: str | None = None
    last_test_sharpe: float | None = None
    last_test_ic: float | None = None
    last_alpha_t: float | None = None
    last_alpha_p: float | None = None
    last_psr: float | None = None
    last_overfit_flag: bool | None = None
    n_runs: int = 0
    created_at: str | None = None
    updated_at: str | None = None


class FactorRunSummary(BaseModel):
    id: str
    factor_id: str
    panel_version: str
    direction: str
    neutralize: str
    benchmark_ticker: str
    top_pct: float
    bottom_pct: float
    transaction_cost_bps: float
    test_sharpe: float
    test_ic: float
    test_psr: float | None = None
    alpha_annualized: float | None = None
    alpha_t: float | None = None
    alpha_p: float | None = None
    beta: float | None = None
    r_squared: float | None = None
    overfit_flag: bool = False
    daily_ic: list[float] | None = None
    ran_at: str | None = None


class FactorDetailResponse(BaseModel):
    factor: FactorSummary
    runs: list[FactorRunSummary]


class DecayAlert(BaseModel):
    factor_id: str
    name: str
    expression: str
    n_runs: int
    baseline_ic: float
    latest_ic: float
    decay_pct: float
    latest_run_at: str


@router.get("", response_model=list[FactorSummary])
def list_factors(limit: int = 100) -> list[FactorSummary]:
    limit = max(1, min(limit, 200))
    rows = _list_factors(limit=limit)
    return [FactorSummary(**r) for r in rows]


@router.get("/decay_alerts", response_model=list[DecayAlert])
def decay_alerts(
    rolling_window_days: int = 60,
    min_runs: int = 3,
    decay_threshold: float = 0.5,
) -> list[DecayAlert]:
    raw = _decay_alerts(
        rolling_window_days=rolling_window_days,
        min_runs=min_runs,
        decay_threshold=decay_threshold,
    )
    return [DecayAlert(**a) for a in raw]


@router.get("/{factor_id}", response_model=FactorDetailResponse)
def get_factor(factor_id: str) -> FactorDetailResponse:
    matches = [f for f in _list_factors(limit=200) if f["id"] == factor_id]
    if not matches:
        raise HTTPException(status_code=404, detail=f"factor {factor_id!r} not found")
    runs = _get_factor_runs(factor_id, limit=200)
    return FactorDetailResponse(
        factor=FactorSummary(**matches[0]),
        runs=[FactorRunSummary(**r) for r in runs],
    )


@router.delete("/{factor_id}")
def delete_factor(factor_id: str) -> dict[str, Any]:
    if not _delete_factor(factor_id):
        raise HTTPException(status_code=404, detail=f"factor {factor_id!r} not found")
    return {"deleted": factor_id}
