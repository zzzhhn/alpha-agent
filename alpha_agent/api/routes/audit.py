"""GET /api/audit — Trade audit log endpoint."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone

from fastapi import APIRouter, Request

from alpha_agent.api.cache import TTLCache
from alpha_agent.models.features import compute_features
from alpha_agent.models.fusion import fuse_predictions
from alpha_agent.models.trainer import _fetch_training_data, get_or_train_models
from alpha_agent.trading.decision_engine import TradingDecision
from alpha_agent.trading.gate import evaluate_gates

router = APIRouter(prefix="/api", tags=["audit"])


@router.get("/audit")
async def audit_log(request: Request) -> dict:
    """Return current trading decision as a single audit entry."""
    cache: TTLCache = request.app.state.cache
    settings = request.app.state.settings

    cached = cache.get("audit_log")
    if cached is not None:
        return cached

    primary = settings.dashboard_tickers[0]
    entries: list[dict] = []

    try:
        models = get_or_train_models()
        ohlcv = _fetch_training_data(settings.dashboard_tickers)
        feats = compute_features(ohlcv, primary)

        # Get predictions from each sub-model
        xgb_pred = models.xgboost.predict(feats)
        lstm_pred = models.lstm.predict(feats)
        hmm_state = models.hmm.predict(feats)

        # Fuse predictions
        preds = {"XGBoost": xgb_pred, "LSTM": lstm_pred}
        hmm_bull_bias = hmm_state.regime_probabilities.get("bull", 0.5)
        fusion = fuse_predictions(preds, hmm_bull_bias=hmm_bull_bias)

        # Evaluate gates
        gate = evaluate_gates(primary)

        # Build rule-based decision (no LLM needed for audit snapshot)
        decision = TradingDecision(
            direction=fusion.direction,
            confidence=round(fusion.confidence * 100, 2),
            position_size_pct=round(min(fusion.confidence * 15, 15.0), 2),
            leverage=round(min(1.0 + fusion.confidence, 3.0), 2),
            ticker=primary,
            reasoning=f"Audit snapshot: fusion={fusion.direction}, gate={'passed' if gate.passed else 'failed'}",
            source="Rule-based fallback",
        )

        entry = asdict(decision)
        entry["timestamp"] = datetime.now(timezone.utc).isoformat()
        entries.append(entry)

    except Exception:
        entries = []

    result = {
        "entries": entries,
        "total_entries": len(entries),
        "filters": {"available_tickers": settings.dashboard_tickers},
    }

    cache.set("audit_log", result, settings.dashboard_cache_ttl_seconds)
    return result
