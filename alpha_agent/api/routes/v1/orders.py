"""v1 Orders endpoints — pending orders and order history."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Request

from alpha_agent.api.cache import TTLCache
from alpha_agent.api.routes.v1.schemas import (
    OrderHistoryResponse,
    PendingOrdersResponse,
)
from alpha_agent.trading.gate import evaluate_gates

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("/pending", response_model=PendingOrdersResponse)
async def pending_orders(request: Request) -> PendingOrdersResponse:
    """Return all pending (unexecuted) orders."""
    cache: TTLCache = request.app.state.cache
    settings = request.app.state.settings

    cached = cache.get("v1_orders_pending")
    if cached is not None:
        return cached

    # Currently paper-only: no real pending orders.
    # Gate evaluation determines whether orders *would* be placed.
    result = PendingOrdersResponse(
        pending_orders=[],
        execution_config={
            "mode": "paper",
            "broker": "none",
            "max_position_pct": 15,
            "max_leverage": 3,
        },
    )

    cache.set("v1_orders_pending", result, settings.dashboard_cache_ttl_seconds)
    return result


@router.get("/history", response_model=OrderHistoryResponse)
async def order_history(request: Request) -> OrderHistoryResponse:
    """Return executed order history."""
    cache: TTLCache = request.app.state.cache
    settings = request.app.state.settings

    cached = cache.get("v1_orders_history")
    if cached is not None:
        return cached

    # Paper mode: no real execution history yet.
    result = OrderHistoryResponse(orders=[], total=0)

    cache.set(
        "v1_orders_history", result, settings.dashboard_cache_ttl_seconds
    )
    return result
