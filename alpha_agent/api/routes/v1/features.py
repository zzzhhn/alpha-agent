"""v1 Feature endpoints — feature state, statistics, and heatmap data."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from alpha_agent.api.cache import TTLCache
from alpha_agent.api.routes.v1.schemas import (
    FeatureStateResponse,
    FeatureStatsResponse,
    FeatureStatRow,
    FeatureValue,
)
from alpha_agent.models.features import (
    compute_features_rich,
    compute_feature_stats,
)
from alpha_agent.models.trainer import _fetch_training_data

router = APIRouter(prefix="/features", tags=["features"])

_CACHE_TTL = 300


@router.get("/state", response_model=list[FeatureStateResponse])
async def feature_state(
    request: Request,
    tickers: str = Query(
        default="",
        description="Comma-separated tickers (e.g. AAPL,MSFT). "
        "Defaults to all configured tickers.",
    ),
) -> list[FeatureStateResponse]:
    """Return feature state with z-scores for requested tickers.

    Blueprint p9: GET /api/v1/features/state?tickers=AAPL,MSFT,...
    """
    cache: TTLCache = request.app.state.cache
    settings = request.app.state.settings

    ticker_list = (
        [t.strip() for t in tickers.split(",") if t.strip()]
        if tickers
        else settings.dashboard_tickers
    )

    cache_key = f"v1_features_state_{'_'.join(sorted(ticker_list))}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        ohlcv = _fetch_training_data(ticker_list)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Failed to fetch market data: {exc}",
        ) from exc

    results: list[FeatureStateResponse] = []
    for ticker in ticker_list:
        rich = compute_features_rich(ohlcv, ticker)
        results.append(FeatureStateResponse(
            ticker=rich["ticker"],
            timestamp=rich["timestamp"],
            features=[
                FeatureValue(**f) for f in rich["features"]
            ],
        ))

    cache.set(cache_key, results, _CACHE_TTL)
    return results


@router.get("/stats/{ticker}", response_model=FeatureStatsResponse)
async def feature_stats(ticker: str, request: Request) -> FeatureStatsResponse:
    """Return summary statistics for all features of a ticker.

    Blueprint p9: GET /api/v1/features/stats/{ticker}
    """
    cache: TTLCache = request.app.state.cache
    settings = request.app.state.settings

    cache_key = f"v1_features_stats_{ticker}"
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
        stats = compute_feature_stats(ohlcv, ticker)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Feature stats computation failed: {exc}",
        ) from exc

    result = FeatureStatsResponse(
        ticker=ticker,
        stats=[FeatureStatRow(**s) for s in stats],
    )

    cache.set(cache_key, result, _CACHE_TTL)
    return result
