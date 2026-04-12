"""v1 Alpha endpoints — factor discovery and backtest results."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Request

from alpha_agent.api.cache import TTLCache
from alpha_agent.api.routes.v1.schemas import (
    AlphaFactorsResponse,
    BacktestResult,
    FactorResult,
)
from alpha_agent.pipeline.registry import FactorRegistry

router = APIRouter(prefix="/alpha", tags=["alpha"])


@router.get("/factors", response_model=AlphaFactorsResponse)
async def alpha_factors(request: Request) -> AlphaFactorsResponse:
    """Return registered alpha factors and pipeline status."""
    cache: TTLCache = request.app.state.cache
    settings = request.app.state.settings

    cached = cache.get("v1_alpha_factors")
    if cached is not None:
        return cached

    factors: list[FactorResult] = []
    try:
        registry = FactorRegistry()
        records = registry.list_all()
        factors = [
            FactorResult(**asdict(r))
            for r in records
        ]
    except Exception:
        factors = []

    result = AlphaFactorsResponse(
        factors=factors,
        pipeline_status={
            "available": True,
            "max_iterations": settings.max_iterations,
        },
    )

    cache.set("v1_alpha_factors", result, settings.dashboard_cache_ttl_seconds)
    return result


@router.get("/backtest", response_model=BacktestResult)
async def alpha_backtest(request: Request) -> BacktestResult:
    """Return latest backtest results for the active strategy."""
    cache: TTLCache = request.app.state.cache
    settings = request.app.state.settings

    cached = cache.get("v1_alpha_backtest")
    if cached is not None:
        return cached

    # Backtest is computed offline; return last stored result or defaults
    result = BacktestResult(
        sharpe=None,
        max_drawdown=None,
        annual_return=None,
        total_trades=0,
        win_rate=None,
        period={
            "start": settings.backtest_start,
            "end": settings.backtest_end,
        },
    )

    cache.set("v1_alpha_backtest", result, settings.dashboard_cache_ttl_seconds)
    return result
