"""GET /api/inference — direction prediction from XGBoost + LSTM + fusion."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Request

from alpha_agent.api.cache import TTLCache
from alpha_agent.models.features import compute_features
from alpha_agent.models.fusion import fuse_predictions
from alpha_agent.models.trainer import get_or_train_models, _fetch_training_data
from alpha_agent.models.xgboost_model import DirectionPrediction

router = APIRouter(prefix="/api", tags=["models"])


@router.get("/inference")
async def inference(request: Request) -> dict:
    """Return per-ticker direction predictions and fused consensus."""
    cache: TTLCache = request.app.state.cache
    settings = request.app.state.settings

    cached = cache.get("inference")
    if cached is not None:
        return cached

    models = get_or_train_models()
    ohlcv = _fetch_training_data(settings.dashboard_tickers)

    assets = []
    all_xgb: dict[str, DirectionPrediction] = {}
    all_lstm: dict[str, DirectionPrediction] = {}

    for ticker in settings.dashboard_tickers:
        features = compute_features(ohlcv, ticker)
        if features.empty:
            continue

        xgb_pred = models.xgboost.predict(features)
        lstm_pred = models.lstm.predict(features)

        # Replace empty ticker with actual ticker
        xgb_pred = DirectionPrediction(
            ticker=ticker,
            bull_prob=xgb_pred.bull_prob,
            bear_prob=xgb_pred.bear_prob,
            direction=xgb_pred.direction,
        )
        lstm_pred = DirectionPrediction(
            ticker=ticker,
            bull_prob=lstm_pred.bull_prob,
            bear_prob=lstm_pred.bear_prob,
            direction=lstm_pred.direction,
        )

        all_xgb[ticker] = xgb_pred
        all_lstm[ticker] = lstm_pred

        assets.append({
            "ticker": ticker,
            "xgboost": asdict(xgb_pred),
            "lstm": asdict(lstm_pred),
            "consensus_direction": xgb_pred.direction if xgb_pred.bull_prob > lstm_pred.bull_prob else lstm_pred.direction,
        })

    # Overall fusion using first ticker
    primary = settings.dashboard_tickers[0]
    fusion_input = {}
    if primary in all_xgb:
        fusion_input["XGBoost"] = all_xgb[primary]
    if primary in all_lstm:
        fusion_input["LSTM"] = all_lstm[primary]

    fusion = fuse_predictions(fusion_input, hmm_bull_bias=0.55)

    result = {
        "assets": assets,
        "fusion": {
            "direction": fusion.direction,
            "confidence": fusion.confidence,
            "bull_prob": fusion.bull_prob,
            "bear_prob": fusion.bear_prob,
        },
        "source": "Real model output (GradientBoosting + MLP)",
    }

    cache.set("inference", result, settings.dashboard_cache_ttl_seconds)
    return result
