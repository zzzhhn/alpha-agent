"""v1 Dashboard endpoint — aggregated summary of all modules."""

from __future__ import annotations

import logging
import time
from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Request

from alpha_agent.api.cache import TTLCache
from alpha_agent.api.routes.v1.schemas import DashboardSummaryResponse
from alpha_agent.config import get_settings
from alpha_agent.llm.ollama import OllamaClient
from alpha_agent.models.features import compute_features
from alpha_agent.models.fusion import fuse_predictions
from alpha_agent.models.hmm import REGIME_LABELS_ZH
from alpha_agent.models.trainer import _fetch_training_data, get_or_train_models
from alpha_agent.models.xgboost_model import DirectionPrediction
from alpha_agent.trading.decision_engine import LLMDecisionEngine
from alpha_agent.trading.gate import evaluate_gates

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _build_asset_predictions(models, ohlcv, tickers):
    """Compute per-ticker predictions. Returns (assets, primary_xgb, primary_lstm)."""
    assets: list[dict] = []
    primary_xgb = None
    primary_lstm = None
    primary = tickers[0]

    for ticker in tickers:
        tk_features = compute_features(ohlcv, ticker)
        if tk_features.empty:
            continue

        xgb = models.xgboost.predict(tk_features)
        lstm = models.lstm.predict(tk_features)

        xgb = DirectionPrediction(
            ticker=ticker,
            bull_prob=xgb.bull_prob,
            bear_prob=xgb.bear_prob,
            direction=xgb.direction,
        )
        lstm = DirectionPrediction(
            ticker=ticker,
            bull_prob=lstm.bull_prob,
            bear_prob=lstm.bear_prob,
            direction=lstm.direction,
        )

        if ticker == primary:
            primary_xgb = xgb
            primary_lstm = lstm

        avg_bull = (xgb.bull_prob + lstm.bull_prob) / 2
        assets.append({
            "ticker": ticker,
            "bull_prob": round(avg_bull, 4),
            "bear_prob": round(1 - avg_bull, 4),
            "direction": "Bullish" if avg_bull > 0.5 else "Bearish",
            "xgboost_score": round(xgb.bull_prob * 100, 2),
            "lstm_score": round(lstm.bull_prob * 100, 2),
        })

    return assets, primary_xgb, primary_lstm


@router.get("/summary", response_model=DashboardSummaryResponse)
async def dashboard_summary(request: Request) -> DashboardSummaryResponse:
    """Aggregated endpoint returning market state, inference, gate, and decision."""
    cache: TTLCache = request.app.state.cache
    settings = request.app.state.settings

    cached = cache.get("v1_dashboard_summary")
    if cached is not None:
        return cached

    start_time = time.monotonic()

    try:
        models = get_or_train_models()
        ohlcv = _fetch_training_data(settings.dashboard_tickers)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Model loading failed: {exc}",
        ) from exc

    primary = settings.dashboard_tickers[0]
    features = compute_features(ohlcv, primary)
    market_state = models.hmm.predict(features)

    assets, primary_xgb, primary_lstm = _build_asset_predictions(
        models, ohlcv, settings.dashboard_tickers
    )

    # Fusion
    hmm_bull = (
        market_state.regime_probabilities.get("Trend", 0)
        + market_state.regime_probabilities.get("Arbitrage", 0)
    )
    fusion_input: dict = {}
    if primary_xgb:
        fusion_input["XGBoost"] = primary_xgb
    if primary_lstm:
        fusion_input["LSTM"] = primary_lstm

    fusion = fuse_predictions(fusion_input, hmm_bull_bias=min(hmm_bull, 1.0))

    # Gate
    gate_result = evaluate_gates(primary)

    # LLM Decision
    ollama = OllamaClient(
        base_url=settings.ollama_base_url,
        model=settings.ollama_model,
    )
    try:
        engine = LLMDecisionEngine(ollama_client=ollama)
        decision = await engine.decide(
            primary, market_state, fusion, gate_result
        )
    finally:
        await ollama.close()

    elapsed = time.monotonic() - start_time

    xgb_bull = primary_xgb.bull_prob if primary_xgb else 0.5
    lstm_bull = primary_lstm.bull_prob if primary_lstm else 0.5

    result = DashboardSummaryResponse(
        market_state={
            "current_regime": market_state.current_regime,
            "current_regime_zh": REGIME_LABELS_ZH.get(
                market_state.current_regime, ""
            ),
            "regime_probabilities": {
                k: round(v * 100, 2)
                for k, v in market_state.regime_probabilities.items()
            },
            "transition_probability": round(
                market_state.transition_probability * 100, 2
            ),
            "model_scores": {
                "HMM": round(
                    market_state.model_scores.get("HMM", 0), 2
                ),
                "XGBoost": round(xgb_bull * 100, 2),
                "LSTM": round(lstm_bull * 100, 2),
                "Fusion": round(fusion.bull_prob * 100, 2),
            },
            "source": "Real model output",
        },
        inference={
            "assets": assets,
            "consensus_direction": fusion.direction,
            "consensus_confidence": round(fusion.confidence * 100, 2),
        },
        gate={
            "ticker": primary,
            "gates": [asdict(g) for g in gate_result.gates],
            "overall_confidence": round(
                gate_result.overall_confidence * 100, 2
            ),
            "passed": gate_result.passed,
            "signal_description": gate_result.signal_description,
        },
        decision=asdict(decision),
        model_voting=[
            {
                "model": "XGBoost",
                "description": "Gradient Boosted Decision Trees",
                "score": round(xgb_bull * 100, 2),
                "direction": primary_xgb.direction if primary_xgb else "N/A",
                "source": "sklearn GradientBoostingClassifier",
            },
            {
                "model": "LSTM",
                "description": "Neural Network (MLP proxy)",
                "score": round(lstm_bull * 100, 2),
                "direction": (
                    primary_lstm.direction if primary_lstm else "N/A"
                ),
                "source": "sklearn MLPClassifier",
            },
            {
                "model": "Fusion",
                "description": "Weighted Model Ensemble",
                "score": round(fusion.bull_prob * 100, 2),
                "direction": fusion.direction,
                "source": "HMM 0.2 + XGBoost 0.45 + LSTM 0.35",
            },
        ],
        meta={
            "tickers": settings.dashboard_tickers,
            "compute_time_ms": round(elapsed * 1000, 1),
            "cached": False,
        },
    )

    cache.set(
        "v1_dashboard_summary", result, settings.dashboard_cache_ttl_seconds
    )
    return result
