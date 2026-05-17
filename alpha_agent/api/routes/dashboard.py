"""GET /api/dashboard — aggregated endpoint returning all dashboard data."""

from __future__ import annotations

import logging
import time
from dataclasses import asdict

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse

from alpha_agent.api.byok import get_llm_client as _get_llm_client
from alpha_agent.api.cache import TTLCache
from alpha_agent.llm.base import LLMClient as _LLMClient
from alpha_agent.models.features import compute_features
from alpha_agent.models.fusion import fuse_predictions
from alpha_agent.models.hmm import REGIME_LABELS_ZH
from alpha_agent.models.trainer import get_or_train_models, _fetch_training_data
from alpha_agent.models.xgboost_model import DirectionPrediction
from alpha_agent.trading.decision_engine import LLMDecisionEngine
from alpha_agent.trading.gate import evaluate_gates

logger = logging.getLogger(__name__)

router = APIRouter(tags=["dashboard"])


@router.get("/qcore")
async def serve_dashboard() -> FileResponse:
    """Serve the dashboard HTML page."""
    from pathlib import Path
    html_path = Path(__file__).resolve().parent.parent.parent.parent / "qcore_dashboard.html"
    return FileResponse(html_path, media_type="text/html")


@router.get("/api/dashboard")
async def dashboard(
    request: Request,
    llm: _LLMClient = Depends(_get_llm_client),
) -> dict:
    """Single endpoint aggregating market state, inference, gate, and decision."""
    cache: TTLCache = request.app.state.cache
    settings = request.app.state.settings

    cached = cache.get("dashboard")
    if cached is not None:
        return cached

    start_time = time.monotonic()

    # --- Train / load models ---
    models = get_or_train_models()
    ohlcv = _fetch_training_data(settings.dashboard_tickers)
    primary = settings.dashboard_tickers[0]
    features = compute_features(ohlcv, primary)

    # --- Market State (HMM) ---
    market_state = models.hmm.predict(features)

    # --- Per-asset inference ---
    assets = []
    primary_xgb = None
    primary_lstm = None

    for ticker in settings.dashboard_tickers:
        tk_features = compute_features(ohlcv, ticker)
        if tk_features.empty:
            continue

        xgb = models.xgboost.predict(tk_features)
        lstm = models.lstm.predict(tk_features)

        xgb = DirectionPrediction(ticker=ticker, bull_prob=xgb.bull_prob, bear_prob=xgb.bear_prob, direction=xgb.direction)
        lstm = DirectionPrediction(ticker=ticker, bull_prob=lstm.bull_prob, bear_prob=lstm.bear_prob, direction=lstm.direction)

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

    # --- Fusion ---
    hmm_bull = (
        market_state.regime_probabilities.get("Trend", 0)
        + market_state.regime_probabilities.get("Arbitrage", 0)
    )
    fusion_input = {}
    if primary_xgb:
        fusion_input["XGBoost"] = primary_xgb
    if primary_lstm:
        fusion_input["LSTM"] = primary_lstm

    fusion = fuse_predictions(fusion_input, hmm_bull_bias=min(hmm_bull, 1.0))

    # --- Gate ---
    gate_result = evaluate_gates(primary)

    # --- LLM Decision (Phase 1 BYOK — `llm` injected by dependency) ---
    engine = LLMDecisionEngine(llm_client=llm)
    decision = await engine.decide(primary, market_state, fusion, gate_result)

    elapsed = time.monotonic() - start_time

    result = {
        "market_state": {
            "current_regime": market_state.current_regime,
            "current_regime_zh": REGIME_LABELS_ZH.get(market_state.current_regime, ""),
            "regime_probabilities": {
                k: round(v * 100, 2) for k, v in market_state.regime_probabilities.items()
            },
            "transition_probability": round(market_state.transition_probability * 100, 2),
            "model_scores": {
                "HMM": round(market_state.model_scores.get("HMM", 0), 2),
                "XGBoost": round((primary_xgb.bull_prob if primary_xgb else 0.5) * 100, 2),
                "LSTM": round((primary_lstm.bull_prob if primary_lstm else 0.5) * 100, 2),
                "Fusion": round(fusion.bull_prob * 100, 2),
            },
            "source": "Real model output",
        },
        "inference": {
            "assets": assets,
            "consensus_direction": fusion.direction,
            "consensus_confidence": round(fusion.confidence * 100, 2),
        },
        "gate": {
            "ticker": primary,
            "gates": [asdict(g) for g in gate_result.gates],
            "overall_confidence": round(gate_result.overall_confidence * 100, 2),
            "passed": gate_result.passed,
            "signal_description": gate_result.signal_description,
        },
        "decision": asdict(decision),
        "model_voting": [
            {
                "model": "XGBoost",
                "description": "Gradient Boosted Decision Trees",
                "score": round((primary_xgb.bull_prob if primary_xgb else 0.5) * 100, 2),
                "direction": primary_xgb.direction if primary_xgb else "N/A",
                "source": "sklearn GradientBoostingClassifier",
            },
            {
                "model": "LSTM",
                "description": "Neural Network (MLP proxy)",
                "score": round((primary_lstm.bull_prob if primary_lstm else 0.5) * 100, 2),
                "direction": primary_lstm.direction if primary_lstm else "N/A",
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
        "meta": {
            "tickers": settings.dashboard_tickers,
            "compute_time_ms": round(elapsed * 1000, 1),
            "cached": False,
        },
    }

    cache.set("dashboard", result, settings.dashboard_cache_ttl_seconds)
    return result
