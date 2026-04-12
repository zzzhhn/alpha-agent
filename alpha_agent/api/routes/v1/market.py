"""v1 Market endpoints — regime detection and technical indicators."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from alpha_agent.api.cache import TTLCache
from alpha_agent.api.routes.v1.schemas import (
    IndicatorValue,
    MarketRegime,
    TickerIndicators,
)
from alpha_agent.models.features import compute_features
from alpha_agent.models.hmm import REGIME_LABELS_ZH
from alpha_agent.models.trainer import _fetch_training_data, get_or_train_models

router = APIRouter(prefix="/market", tags=["market"])

_CACHE_TTL = 300


def _df_to_records(df) -> list[dict]:
    """Convert a DataFrame to JSON-safe list of dicts."""
    out = df.reset_index()
    for col in out.columns:
        if hasattr(out[col], "dt"):
            out[col] = out[col].astype(str)
    return out.to_dict(orient="records")


@router.get("/state", response_model=MarketRegime)
async def market_state(request: Request) -> MarketRegime:
    """Detect current market regime via HMM."""
    cache: TTLCache = request.app.state.cache
    settings = request.app.state.settings

    cached = cache.get("v1_market_state")
    if cached is not None:
        return cached

    try:
        models = get_or_train_models()
        ohlcv = _fetch_training_data(settings.dashboard_tickers)
        primary = settings.dashboard_tickers[0]
        features = compute_features(ohlcv, primary)
        state = models.hmm.predict(features)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Market state computation failed: {exc}",
        ) from exc

    result = MarketRegime(
        current_regime=state.current_regime,
        current_regime_zh=REGIME_LABELS_ZH.get(
            state.current_regime, state.current_regime
        ),
        regime_probabilities=state.regime_probabilities,
        transition_probability=state.transition_probability,
        model_scores=state.model_scores,
        source="Real model output (HMM GaussianHMM)",
    )

    cache.set("v1_market_state", result, settings.dashboard_cache_ttl_seconds)
    return result


@router.get("/indicators/{ticker}", response_model=TickerIndicators)
async def market_indicators(ticker: str, request: Request) -> TickerIndicators:
    """Return technical indicators and recent OHLCV for a ticker."""
    cache: TTLCache = request.app.state.cache
    settings = request.app.state.settings

    cache_key = f"v1_market_indicators_{ticker}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    allowed_tickers = settings.dashboard_tickers
    if ticker not in allowed_tickers:
        raise HTTPException(
            status_code=404,
            detail=f"Ticker '{ticker}' not in monitored universe: {allowed_tickers}",
        )

    try:
        ohlcv = _fetch_training_data(allowed_tickers)
        ticker_ohlcv = ohlcv.xs(ticker, level="stock_code")
        recent_bars = _df_to_records(ticker_ohlcv.tail(20))

        feats = compute_features(ohlcv, ticker)
        last_row = feats.iloc[-1] if not feats.empty else {}
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Indicator computation failed for {ticker}: {exc}",
        ) from exc

    indicators = [
        IndicatorValue(name=col, value=round(float(val), 6))
        for col, val in (last_row.items() if hasattr(last_row, "items") else [])
    ]

    result = TickerIndicators(
        ticker=ticker,
        indicators=indicators,
        ohlcv_recent=recent_bars,
    )

    cache.set(cache_key, result, _CACHE_TTL)
    return result
