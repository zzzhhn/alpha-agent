"""API v1 router aggregation — mounts all v1 sub-routers under /api/v1."""

from __future__ import annotations

from fastapi import APIRouter

from alpha_agent.api.routes.v1.market import router as market_router
from alpha_agent.api.routes.v1.inference import router as inference_router
from alpha_agent.api.routes.v1.alpha import router as alpha_router
from alpha_agent.api.routes.v1.portfolio import router as portfolio_router
from alpha_agent.api.routes.v1.orders import router as orders_router
from alpha_agent.api.routes.v1.gateway import router as gateway_router
from alpha_agent.api.routes.v1.audit import router as audit_router
from alpha_agent.api.routes.v1.system import router as system_router
from alpha_agent.api.routes.v1.dashboard import router as dashboard_router
from alpha_agent.api.routes.v1.features import router as features_router
from alpha_agent.api.routes.v1.data_quality import router as data_quality_router
from alpha_agent.api.routes.v1.auth import router as auth_router

v1_router = APIRouter(prefix="/api/v1")

v1_router.include_router(market_router)
v1_router.include_router(inference_router)
v1_router.include_router(alpha_router)
v1_router.include_router(portfolio_router)
v1_router.include_router(orders_router)
v1_router.include_router(gateway_router)
v1_router.include_router(audit_router)
v1_router.include_router(system_router)
v1_router.include_router(dashboard_router)
v1_router.include_router(features_router)
v1_router.include_router(data_quality_router)
v1_router.include_router(auth_router)

__all__ = ["v1_router"]
