"""FastAPI application factory for the AlphaCore dashboard API."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from alpha_agent.api.cache import TTLCache
from alpha_agent.config import get_settings
from alpha_agent.llm.factory import create_llm_client

logger = logging.getLogger(__name__)

# Shared cache instance — injected into route handlers via app.state
_cache = TTLCache()

# Detect serverless environment (Vercel Functions set AWS_LAMBDA_FUNCTION_NAME)
SERVERLESS = os.environ.get("VERCEL", "") == "1" or os.environ.get("SERVERLESS", "") == "true"


@asynccontextmanager
async def _lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Startup / shutdown logic."""
    settings = get_settings()
    application.state.settings = settings
    application.state.cache = _cache

    # Create shared LLM client — reused across requests (connection pooling)
    llm = create_llm_client(settings)
    application.state.llm = llm

    logger.info(
        "AlphaCore API starting — tickers=%s, llm=%s, serverless=%s",
        settings.dashboard_tickers,
        settings.llm_provider,
        SERVERLESS,
    )

    yield

    # Cleanup LLM client connection pool
    if hasattr(llm, "close"):
        await llm.close()
    logger.info("AlphaCore API shutting down.")


def create_app() -> FastAPI:
    """Build and return the FastAPI application."""
    application = FastAPI(
        title="AlphaCore Dashboard API",
        version="1.0.0",
        lifespan=_lifespan,
    )

    # --- Security middleware (rate limiting always on, auth optional) ----
    from alpha_agent.api.security import SecurityMiddleware
    import os

    auth_enabled = os.environ.get("ALPHACORE_AUTH_ENABLED", "false").lower() == "true"
    application.add_middleware(SecurityMiddleware, auth_enabled=auth_enabled)

    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST"],
        allow_headers=["*", "Authorization"],
    )

    # --- System route (always available — lightweight) ----------------------
    from alpha_agent.api.routes.system import router as system_router

    application.include_router(system_router)

    if SERVERLESS:
        # Lightweight routes only — no ML/data dependencies
        from alpha_agent.api.routes.serverless import router as serverless_router

        application.include_router(serverless_router)
        logger.info("Serverless mode: using LLM-only dashboard routes")
    else:
        # Full ML pipeline routes
        from alpha_agent.api.routes.v1 import v1_router

        application.include_router(v1_router)

        from alpha_agent.api.routes.dashboard import router as dashboard_router
        from alpha_agent.api.routes.decision import router as decision_router
        from alpha_agent.api.routes.gate import router as gate_router
        from alpha_agent.api.routes.inference import router as inference_router
        from alpha_agent.api.routes.market_state import router as market_state_router
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
        application.include_router(market_router)
        application.include_router(alpha_router)
        application.include_router(portfolio_router)
        application.include_router(orders_router)
        application.include_router(audit_router)

    # --- WebSocket endpoints (skip in serverless — no persistent connections) ---
    if not SERVERLESS:
        from alpha_agent.api.websocket import router as ws_router

        application.include_router(ws_router)

    # --- Health check -----------------------------------------------------
    @application.get("/api/health")
    async def health() -> dict:
        return {"status": "ok", "service": "alphacore"}

    # --- Static files (dashboard HTML) — skip in serverless ----------------
    if not SERVERLESS:
        project_root = Path(__file__).resolve().parent.parent.parent
        static_dir = project_root
        if (static_dir / "qcore_dashboard.html").exists():
            application.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    return application


# Module-level app for ``uvicorn alpha_agent.api.app:app``
app = create_app()
