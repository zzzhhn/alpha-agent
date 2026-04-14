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

_cache = TTLCache()

SERVERLESS = (
    os.environ.get("VERCEL", "") == "1"
    or os.environ.get("SERVERLESS", "").lower() == "true"
)

# ── Lazy init (for Vercel where lifespan may not fire) ────────────────────

_initialized = False


def _ensure_initialized(app: FastAPI) -> None:
    global _initialized
    if _initialized:
        return
    _initialized = True
    settings = get_settings()
    app.state.settings = settings
    app.state.cache = _cache
    app.state.llm = create_llm_client(settings)
    logger.info("AlphaCore init (lazy): llm=%s", settings.llm_provider)


# ── Lifespan (used by uvicorn, may be skipped on Vercel) ──────────────────

@asynccontextmanager
async def _lifespan(application: FastAPI) -> AsyncIterator[None]:
    _ensure_initialized(application)
    yield
    llm = getattr(application.state, "llm", None)
    if llm and hasattr(llm, "close"):
        await llm.close()


# ── App factory ───────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    application = FastAPI(
        title="AlphaCore Dashboard API",
        version="1.0.0",
        lifespan=_lifespan if not SERVERLESS else None,
    )

    # In serverless mode, initialize state eagerly at import time
    # (lifespan doesn't fire on Vercel)
    if SERVERLESS:
        import sys
        try:
            _ensure_initialized(application)
        except Exception as e:
            print(f"INIT ERROR: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
            # Set fallback state so health endpoint works
            application.state.settings = get_settings()
            application.state.cache = _cache
            application.state.llm = None

    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST"],
        allow_headers=["*", "Authorization"],
    )

    # Security middleware (skip in serverless — BaseHTTPMiddleware incompatible)
    if not SERVERLESS:
        from alpha_agent.api.security import SecurityMiddleware

        auth_enabled = os.environ.get("ALPHACORE_AUTH_ENABLED", "false").lower() == "true"
        application.add_middleware(SecurityMiddleware, auth_enabled=auth_enabled)

    # System route (always lightweight)
    from alpha_agent.api.routes.system import router as system_router

    application.include_router(system_router)

    # Always load serverless routes — they match frontend TypeScript types exactly
    # and will attempt real ML calls when available (with demo data fallback).
    from alpha_agent.api.routes.serverless import router as serverless_router

    application.include_router(serverless_router)

    # Interactive endpoints (POST — backtest, ticker analysis, search)
    from alpha_agent.api.routes.interactive import router as interactive_router

    application.include_router(interactive_router)

    # LLM provider control (GET status, POST switch)
    from alpha_agent.api.routes.llm_control import router as llm_control_router

    application.include_router(llm_control_router)

    if not SERVERLESS:
        try:
            from alpha_agent.api.websocket import router as ws_router

            application.include_router(ws_router)
        except ImportError:
            logger.info("WebSocket module not available, skipping")

    @application.get("/api/health")
    async def health() -> dict:
        return {"status": "ok", "service": "alphacore", "mode": "serverless" if SERVERLESS else "full"}

    # Redirect root and /qcore to Vercel Next.js frontend
    _FRONTEND_URL = "https://frontend-delta-three-81.vercel.app"

    from fastapi.responses import RedirectResponse

    @application.get("/")
    async def root_redirect():
        return RedirectResponse(_FRONTEND_URL)

    @application.get("/qcore")
    async def qcore_redirect():
        return RedirectResponse(_FRONTEND_URL)

    return application


app = create_app()
