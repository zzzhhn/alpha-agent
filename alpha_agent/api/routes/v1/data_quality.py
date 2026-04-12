"""v1 Data Quality endpoints — OHLCV validation checks."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from alpha_agent.api.cache import TTLCache
from alpha_agent.api.routes.v1.schemas import (
    DataQualityResponse,
    ValidationRuleResult,
)
from alpha_agent.data.quality import validate_ohlcv
from alpha_agent.models.trainer import _fetch_training_data

router = APIRouter(prefix="/data", tags=["data-quality"])

_CACHE_TTL = 60  # Short TTL — quality checks should be relatively fresh


@router.get("/quality/{ticker}", response_model=DataQualityResponse)
async def data_quality(ticker: str, request: Request) -> DataQualityResponse:
    """Run 7 OHLCV validation rules for a ticker.

    Blueprint p9: GET /api/v1/data/quality/{ticker}
    """
    cache: TTLCache = request.app.state.cache
    settings = request.app.state.settings

    cache_key = f"v1_data_quality_{ticker}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    if ticker not in settings.dashboard_tickers:
        raise HTTPException(
            status_code=404,
            detail=f"Ticker '{ticker}' not in monitored universe.",
        )

    try:
        ohlcv = _fetch_training_data(settings.dashboard_tickers)
        report = validate_ohlcv(ohlcv, ticker)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Data quality check failed: {exc}",
        ) from exc

    result = DataQualityResponse(
        ticker=report["ticker"],
        total_rows=report["total_rows"],
        rules=[ValidationRuleResult(**r) for r in report["rules"]],
        overall_pass=report["overall_pass"],
    )

    cache.set(cache_key, result, _CACHE_TTL)
    return result
