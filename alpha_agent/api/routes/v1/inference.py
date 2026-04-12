"""v1 Inference endpoints — model predictions and model registry."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from alpha_agent.api.cache import TTLCache
from alpha_agent.api.routes.v1.schemas import (
    InferencePredictResponse,
    ModelInfo,
    ModelsListResponse,
)
from alpha_agent.models.features import compute_features
from alpha_agent.models.fusion import fuse_predictions
from alpha_agent.models.trainer import _fetch_training_data, get_or_train_models
from alpha_agent.models.xgboost_model import DirectionPrediction

router = APIRouter(prefix="/inference", tags=["inference"])


@router.get("/predict", response_model=InferencePredictResponse)
async def predict(request: Request) -> InferencePredictResponse:
    """Return fused direction predictions across all tickers."""
    cache: TTLCache = request.app.state.cache
    settings = request.app.state.settings

    cached = cache.get("v1_inference_predict")
    if cached is not None:
        return cached

    try:
        models = get_or_train_models()
        ohlcv = _fetch_training_data(settings.dashboard_tickers)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Model loading failed: {exc}",
        ) from exc

    assets: list[dict] = []
    all_xgb: dict[str, DirectionPrediction] = {}
    all_lstm: dict[str, DirectionPrediction] = {}

    for ticker in settings.dashboard_tickers:
        features = compute_features(ohlcv, ticker)
        if features.empty:
            continue

        xgb_pred = models.xgboost.predict(features)
        lstm_pred = models.lstm.predict(features)

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

        consensus = (
            xgb_pred.direction
            if xgb_pred.bull_prob > lstm_pred.bull_prob
            else lstm_pred.direction
        )
        assets.append({
            "ticker": ticker,
            "xgboost": asdict(xgb_pred),
            "lstm": asdict(lstm_pred),
            "consensus_direction": consensus,
        })

    primary = settings.dashboard_tickers[0]
    fusion_input: dict = {}
    if primary in all_xgb:
        fusion_input["XGBoost"] = all_xgb[primary]
    if primary in all_lstm:
        fusion_input["LSTM"] = all_lstm[primary]

    fusion = fuse_predictions(fusion_input, hmm_bull_bias=0.55)

    result = InferencePredictResponse(
        assets=assets,
        fusion={
            "direction": fusion.direction,
            "confidence": fusion.confidence,
            "bull_prob": fusion.bull_prob,
            "bear_prob": fusion.bear_prob,
        },
        source="Real model output (GradientBoosting + MLP)",
    )

    cache.set(
        "v1_inference_predict", result, settings.dashboard_cache_ttl_seconds
    )
    return result


@router.get("/models", response_model=ModelsListResponse)
async def list_models(request: Request) -> ModelsListResponse:
    """Return status of all registered ML models."""
    settings = request.app.state.settings

    model_dir = Path(settings.model_dir)
    joblib_files = (
        list(model_dir.glob("*.joblib")) if model_dir.exists() else []
    )
    file_lookup = {f.stem: f for f in joblib_files}

    model_defs = [
        ("xgboost", "XGBoost direction classifier (GradientBoosting)"),
        ("lstm", "LSTM direction classifier (MLP proxy)"),
        ("hmm", "HMM regime detector (GaussianHMM)"),
    ]

    items: list[ModelInfo] = []
    for name, description in model_defs:
        matched = file_lookup.get(name)
        items.append(
            ModelInfo(
                name=name,
                trained=matched is not None,
                last_trained=(
                    matched.stat().st_mtime if matched else None
                ),
                file=matched.name if matched else None,
                description=description,
            )
        )

    return ModelsListResponse(models=items)
