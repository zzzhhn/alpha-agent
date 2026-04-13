"""FastAPI application factory for the AlphaCore dashboard API."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from alpha_agent.api.cache import TTLCache
from alpha_agent.config import get_settings
from alpha_agent.llm.factory import create_llm_client

logger = logging.getLogger(__name__)

# Shared cache instance
_cache = TTLCache()

# Detect serverless environment
SERVERLESS = (
    os.environ.get("VERCEL", "") == "1"
    or os.environ.get("SERVERLESS", "").lower() == "true"
)

# Lazy-init state — populated on first request (works on Vercel where
# ASGI lifespan events may not fire).
_initialized = False


def _ensure_initialized(app: FastAPI) -> None:
    """Initialize app.state on first request if lifespan didn't run."""
    global _initialized
    if _initialized:
        return
    _initialized = True

    settings = get_settings()
    app.state.settings = settings
    app.state.cache = _cache
    app.state.llm = create_llm_client(settings)

    logger.info(
        "AlphaCore API initialized (lazy) — llm=%s, serverless=%s",
        settings.llm_provider,
        SERVERLESS,
    )


@asynccontextmanager
async def _lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Startup / shutdown — used by uvicorn; may be skipped on Vercel."""
    _ensure_initialized(application)
    yield
    llm = getattr(application.state, "llm", None)
    if llm and hasattr(llm, "close"):
        await llm.close()


def create_app() -> FastAPI:
    """Build and return the FastAPI application."""
    application = FastAPI(
        title="AlphaCore Dashboard API",
        version="1.0.0",
        lifespan=_lifespan if not SERVERLESS else None,
    )

    # --- Lazy-init middleware (Vercel doesn't run lifespan) ----------------
    if SERVERLESS:
        from starlette.middleware.base import BaseHTTPMiddleware
        from starlette.responses import Response

        class LazyInitMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request: Request, call_next):
                _ensure_initialized(request.app)
                return await call_next(request)

        application.add_middleware(LazyInitMiddleware)

    # --- Security middleware -----------------------------------------------
    from alpha_agent.api.security import SecurityMiddleware

    auth_enabled = os.environ.get("ALPHACORE_AUTH_ENABLED", "false").lower() == "true"
    application.add_middleware(SecurityMiddleware, auth_enabled=auth_enabled)

    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST"],
        allow_headers=["*", "Authorization"],
    )

    # --- System route (always lightweight) ---------------------------------
    from alpha_agent.api.routes.system import router as system_router

    application.include_router(system_router)

    if SERVERLESS:
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

    # --- WebSocket (skip in serverless) ------------------------------------
    if not SERVERLESS:
        from alpha_agent.api.websocket import router as ws_router

        application.include_router(ws_router)

    # --- Health check (always available) -----------------------------------
    @application.get("/api/health")
    async def health() -> dict:
        return {"status": "ok", "service": "alphacore", "mode": "serverless" if SERVERLESS else "full"}

    # --- Static files (skip in serverless) ---------------------------------
    if not SERVERLESS:
        from fastapi.staticfiles import StaticFiles

        project_root = Path(__file__).resolve().parent.parent.parent
        if (project_root / "qcore_dashboard.html").exists():
            application.mount("/static", StaticFiles(directory=str(project_root)), name="static")

    return application


# Module-level app instance
app = create_app()
