"""v1 Gateway endpoints — gate check status and rule definitions."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Request

from alpha_agent.api.cache import TTLCache
from alpha_agent.api.routes.v1.schemas import (
    GateCheck,
    GateRule,
    GatewayRulesResponse,
    GatewayStatusResponse,
)
from alpha_agent.trading.gate import evaluate_gates

router = APIRouter(prefix="/gateway", tags=["gateway"])

# Static rule definitions — these describe the multi-timeframe gate logic
_GATE_RULES: list[GateRule] = [
    GateRule(
        name="1m_momentum",
        description="1-minute momentum gate: confirms short-term trend alignment",
        enabled=True,
        threshold=0.5,
    ),
    GateRule(
        name="5m_trend",
        description="5-minute trend gate: validates medium-term direction",
        enabled=True,
        threshold=0.5,
    ),
    GateRule(
        name="15m_structure",
        description="15-minute market structure gate: ensures broader context",
        enabled=True,
        threshold=0.5,
    ),
    GateRule(
        name="volume_confirmation",
        description="Volume surge gate: requires above-average volume",
        enabled=True,
        threshold=1.2,
    ),
]


@router.get("/status", response_model=GatewayStatusResponse)
async def gateway_status(request: Request) -> GatewayStatusResponse:
    """Evaluate all gates for the primary ticker."""
    cache: TTLCache = request.app.state.cache
    settings = request.app.state.settings

    cached = cache.get("v1_gateway_status")
    if cached is not None:
        return cached

    primary = settings.dashboard_tickers[0]

    try:
        gate_result = evaluate_gates(primary)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Gate evaluation failed: {exc}",
        ) from exc

    gates = [
        GateCheck(
            name=g.name,
            passed=g.passed,
            confidence=g.score,
            reason=g.description,
        )
        for g in gate_result.gates
    ]

    result = GatewayStatusResponse(
        ticker=primary,
        gates=gates,
        overall_confidence=gate_result.overall_confidence,
        passed=gate_result.passed,
        signal_description=gate_result.signal_description,
    )

    cache.set(
        "v1_gateway_status", result, settings.dashboard_cache_ttl_seconds
    )
    return result


@router.get("/rules", response_model=GatewayRulesResponse)
async def gateway_rules() -> GatewayRulesResponse:
    """Return all configured gate rule definitions."""
    return GatewayRulesResponse(rules=_GATE_RULES)
