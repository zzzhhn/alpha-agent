"""GET /api/market-state — HMM regime recognition endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Request

from alpha_agent.api.cache import TTLCache
from alpha_agent.models.features import compute_features
from alpha_agent.models.hmm import REGIME_LABELS_ZH
from alpha_agent.models.trainer import get_or_train_models, _fetch_training_data

router = APIRouter(prefix="/api", tags=["models"])


@router.get("/market-state")
async def market_state(request: Request) -> dict:
    """Return current HMM market regime and state probabilities."""
    cache: TTLCache = request.app.state.cache
    settings = request.app.state.settings

    cached = cache.get("market_state")
    if cached is not None:
        return cached

    models = get_or_train_models()
    ohlcv = _fetch_training_data(settings.dashboard_tickers)
    primary = settings.dashboard_tickers[0]
    features = compute_features(ohlcv, primary)

    state = models.hmm.predict(features)

    result = {
        "current_regime": state.current_regime,
        "current_regime_zh": REGIME_LABELS_ZH.get(state.current_regime, state.current_regime),
        "regime_probabilities": state.regime_probabilities,
        "transition_probability": state.transition_probability,
        "model_scores": state.model_scores,
        "source": "Real model output (HMM GaussianHMM)",
    }

    cache.set("market_state", result, settings.dashboard_cache_ttl_seconds)
    return result
