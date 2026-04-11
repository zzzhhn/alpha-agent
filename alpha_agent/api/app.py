"""FastAPI application factory for the AlphaCore dashboard API."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from alpha_agent.api.cache import TTLCache
from alpha_agent.config import get_settings

logger = logging.getLogger(__name__)

# Shared cache instance — injected into route handlers via app.state
_cache = TTLCache()


@asynccontextmanager
async def _lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Startup / shutdown logic."""
    settings = get_settings()
    application.state.settings = settings
    application.state.cache = _cache

    logger.info(
        "AlphaCore API starting — tickers=%s, cache_ttl=%ds",
        settings.dashboard_tickers,
        settings.dashboard_cache_ttl_seconds,
    )

    # Lazy model training on first request (not startup) to keep boot fast
    yield

    logger.info("AlphaCore API shutting down.")


def create_app() -> FastAPI:
    """Build and return the FastAPI application."""
    application = FastAPI(
        title="AlphaCore Dashboard API",
        version="0.1.0",
        lifespan=_lifespan,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    # --- Routes -----------------------------------------------------------
    from alpha_agent.api.routes.dashboard import router as dashboard_router
    from alpha_agent.api.routes.decision import router as decision_router
    from alpha_agent.api.routes.gate import router as gate_router
    from alpha_agent.api.routes.inference import router as inference_router
    from alpha_agent.api.routes.market_state import router as market_state_router
    from alpha_agent.api.routes.system import router as system_router
    from alpha_agent.api.routes.market import router as market_router
    from alpha_agent.api.routes.alpha import router as alpha_router
    from alpha_agent.api.routes.portfolio import router as portfolio_router
    from alpha_agent.api.routes.orders import router as orders_router
    from alpha_agent.api.routes.audit import router as audit_router

    application.include_router(dashboard_router)
    application.include_router(market_state_router)
    application.include_router(inference_router)
    application.include_router(gate_router)
    application.include_router(decision_router)
    application.include_router(system_router)
    application.include_router(market_router)
    application.include_router(alpha_router)
    application.include_router(portfolio_router)
    application.include_router(orders_router)
    application.include_router(audit_router)

    # --- Health check -----------------------------------------------------
    @application.get("/api/health")
    async def health() -> dict:
        return {"status": "ok", "service": "alphacore"}

    # --- Static files (dashboard HTML) ------------------------------------
    project_root = Path(__file__).resolve().parent.parent.parent
    static_dir = project_root
    if (static_dir / "qcore_dashboard.html").exists():
        application.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    return application


# Module-level app for ``uvicorn alpha_agent.api.app:app``
app = create_app()
