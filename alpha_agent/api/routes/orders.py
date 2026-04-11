"""GET /api/orders — Order execution gateway endpoint."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Request

from alpha_agent.api.cache import TTLCache
from alpha_agent.trading.gate import evaluate_gates

router = APIRouter(prefix="/api", tags=["orders"])


@router.get("/orders")
async def orders_view(request: Request) -> dict:
    """Return gate evaluation, pending orders, and execution config."""
    cache: TTLCache = request.app.state.cache
    settings = request.app.state.settings

    cached = cache.get("orders_view")
    if cached is not None:
        return cached

    primary_ticker = settings.dashboard_tickers[0]

    # Evaluate multi-timeframe gates
    try:
        gate_result = evaluate_gates(primary_ticker)
        gate_dict = asdict(gate_result)
    except Exception:
        gate_dict = {"error": "Gate evaluation failed", "passed": False}

    result = {
        "gate": gate_dict,
        "pending_orders": [],
        "execution_config": {
            "mode": "paper",
            "broker": "none",
            "max_position_pct": 15,
            "max_leverage": 3,
        },
        "signal_history": [],
    }

    cache.set("orders_view", result, settings.dashboard_cache_ttl_seconds)
    return result
