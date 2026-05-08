"""GET /api/decision — LLM-powered trading decision endpoint."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, Request

from alpha_agent.api.byok import get_llm_client as _get_llm_client
from alpha_agent.api.cache import TTLCache
from alpha_agent.config import get_settings
from alpha_agent.llm.base import LLMClient as _LLMClient
from alpha_agent.models.features import compute_features
from alpha_agent.models.fusion import fuse_predictions
from alpha_agent.models.trainer import get_or_train_models, _fetch_training_data
from alpha_agent.models.xgboost_model import DirectionPrediction
from alpha_agent.trading.decision_engine import LLMDecisionEngine
from alpha_agent.trading.gate import evaluate_gates

router = APIRouter(prefix="/api", tags=["trading"])


@router.get("/decision")
async def decision(
    request: Request,
    llm: _LLMClient = Depends(_get_llm_client),
) -> dict:
    """Return the final LLM trading decision with full reasoning."""
    cache: TTLCache = request.app.state.cache
    settings = request.app.state.settings

    cached = cache.get("decision")
    if cached is not None:
        return cached

    primary = settings.dashboard_tickers[0]

    # Get all sub-model outputs
    models = get_or_train_models()
    ohlcv = _fetch_training_data(settings.dashboard_tickers)
    features = compute_features(ohlcv, primary)

    market_state = models.hmm.predict(features)
    xgb_pred = models.xgboost.predict(features)
    lstm_pred = models.lstm.predict(features)

    xgb_pred = DirectionPrediction(
        ticker=primary,
        bull_prob=xgb_pred.bull_prob,
        bear_prob=xgb_pred.bear_prob,
        direction=xgb_pred.direction,
    )
    lstm_pred = DirectionPrediction(
        ticker=primary,
        bull_prob=lstm_pred.bull_prob,
        bear_prob=lstm_pred.bear_prob,
        direction=lstm_pred.direction,
    )

    fusion = fuse_predictions(
        {"XGBoost": xgb_pred, "LSTM": lstm_pred},
        hmm_bull_bias=market_state.regime_probabilities.get("Trend", 0.3)
        + market_state.regime_probabilities.get("Arbitrage", 0.2),
    )

    gate_result = evaluate_gates(primary)

    # LLM decision (Phase 1 BYOK — `llm` injected by dependency)
    engine = LLMDecisionEngine(llm_client=llm)
    trading_decision = await engine.decide(primary, market_state, fusion, gate_result)

    result = {
        "decision": asdict(trading_decision),
        "market_state": {
            "current_regime": market_state.current_regime,
            "transition_probability": market_state.transition_probability,
        },
        "fusion": {
            "direction": fusion.direction,
            "confidence": fusion.confidence,
        },
        "gate": {
            "passed": gate_result.passed,
            "overall_confidence": gate_result.overall_confidence,
        },
        "source": "LLM decision (Gemma 4 26B via Ollama)" if trading_decision.source.startswith("LLM") else trading_decision.source,
    }

    cache.set("decision", result, settings.dashboard_cache_ttl_seconds)
    return result
