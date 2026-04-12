"""v1 Audit endpoints — audit trail and decision history."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from alpha_agent.api.cache import TTLCache
from alpha_agent.api.routes.v1.schemas import (
    AuditEntry,
    AuditLogResponse,
    DecisionEntry,
    DecisionHistoryResponse,
)
from alpha_agent.models.features import compute_features
from alpha_agent.models.fusion import fuse_predictions
from alpha_agent.models.trainer import _fetch_training_data, get_or_train_models
from alpha_agent.trading.decision_engine import TradingDecision
from alpha_agent.trading.gate import evaluate_gates

router = APIRouter(prefix="/audit", tags=["audit"])


def _build_current_decision(settings) -> TradingDecision | None:
    """Build a rule-based trading decision snapshot for audit."""
    primary = settings.dashboard_tickers[0]
    try:
        models = get_or_train_models()
        ohlcv = _fetch_training_data(settings.dashboard_tickers)
        feats = compute_features(ohlcv, primary)

        xgb_pred = models.xgboost.predict(feats)
        lstm_pred = models.lstm.predict(feats)
        hmm_state = models.hmm.predict(feats)

        preds = {"XGBoost": xgb_pred, "LSTM": lstm_pred}
        hmm_bull_bias = hmm_state.regime_probabilities.get("bull", 0.5)
        fusion = fuse_predictions(preds, hmm_bull_bias=hmm_bull_bias)

        gate = evaluate_gates(primary)

        return TradingDecision(
            direction=fusion.direction,
            confidence=round(fusion.confidence * 100, 2),
            position_size_pct=round(min(fusion.confidence * 15, 15.0), 2),
            leverage=round(min(1.0 + fusion.confidence, 3.0), 2),
            ticker=primary,
            reasoning=(
                f"Audit snapshot: fusion={fusion.direction}, "
                f"gate={'passed' if gate.passed else 'failed'}"
            ),
            source="Rule-based fallback",
        )
    except Exception:
        return None


@router.get("/log", response_model=AuditLogResponse)
async def audit_log(request: Request) -> AuditLogResponse:
    """Return the audit trail of trading decisions."""
    cache: TTLCache = request.app.state.cache
    settings = request.app.state.settings

    cached = cache.get("v1_audit_log")
    if cached is not None:
        return cached

    decision = _build_current_decision(settings)
    entries: list[AuditEntry] = []

    if decision is not None:
        entries.append(
            AuditEntry(
                timestamp=datetime.now(timezone.utc).isoformat(),
                ticker=decision.ticker,
                direction=decision.direction,
                confidence=decision.confidence,
                reasoning=decision.reasoning,
                source=decision.source,
            )
        )

    result = AuditLogResponse(
        entries=entries,
        total_entries=len(entries),
        filters={"available_tickers": settings.dashboard_tickers},
    )

    cache.set("v1_audit_log", result, settings.dashboard_cache_ttl_seconds)
    return result


@router.get("/decisions", response_model=DecisionHistoryResponse)
async def decision_history(request: Request) -> DecisionHistoryResponse:
    """Return historical trading decisions."""
    cache: TTLCache = request.app.state.cache
    settings = request.app.state.settings

    cached = cache.get("v1_audit_decisions")
    if cached is not None:
        return cached

    decision = _build_current_decision(settings)
    decisions: list[DecisionEntry] = []

    if decision is not None:
        d = asdict(decision)
        decisions.append(
            DecisionEntry(
                timestamp=datetime.now(timezone.utc).isoformat(),
                ticker=d.get("ticker", ""),
                direction=d.get("direction", ""),
                confidence=d.get("confidence", 0.0),
                position_size_pct=d.get("position_size_pct", 0.0),
                leverage=d.get("leverage", 1.0),
                reasoning=d.get("reasoning", ""),
                source=d.get("source", ""),
            )
        )

    result = DecisionHistoryResponse(
        decisions=decisions,
        total=len(decisions),
    )

    cache.set(
        "v1_audit_decisions", result, settings.dashboard_cache_ttl_seconds
    )
    return result
