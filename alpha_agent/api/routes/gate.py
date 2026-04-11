"""GET /api/gate — multi-timeframe trading gate evaluation."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Request

from alpha_agent.api.cache import TTLCache
from alpha_agent.trading.gate import evaluate_gates

router = APIRouter(prefix="/api", tags=["trading"])


@router.get("/gate")
async def gate(request: Request) -> dict:
    """Return multi-timeframe gate evaluation for the primary ticker."""
    cache: TTLCache = request.app.state.cache
    settings = request.app.state.settings

    cached = cache.get("gate")
    if cached is not None:
        return cached

    primary = settings.dashboard_tickers[0]
    gate_result = evaluate_gates(primary)

    result = {
        "ticker": primary,
        "gates": [asdict(g) for g in gate_result.gates],
        "overall_confidence": gate_result.overall_confidence,
        "passed": gate_result.passed,
        "signal_description": gate_result.signal_description,
        "source": "Real market data (yfinance intraday)",
    }

    cache.set("gate", result, settings.dashboard_cache_ttl_seconds)
    return result
