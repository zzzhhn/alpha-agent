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
from alpha_agent.core.exceptions import ProviderUnavailableError
from alpha_agent.core.types import RouterHealth
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
    # Phase 1 BYOK — platform LLM is now optional. Public deploys set
    # ALPHACORE_REQUIRE_BYOK=true and leave provider keys unset; the
    # `byok.get_llm_client` dependency builds one per request from the
    # caller's headers. We still try to construct a platform client here
    # so local dev (with KIMI_API_KEY in .env) keeps the legacy "no
    # BYOK headers required" flow. Construction failure (no key) is now
    # warned, not fatal — see feedback_silent_trycatch_antipattern.md;
    # we surface the reason via app.state.llm_init_error so /healthz can
    # report it.
    try:
        app.state.llm = create_llm_client(settings)
        app.state.llm_init_error = None
    except Exception as exc:  # noqa: BLE001 — surfaced via /healthz
        app.state.llm = None
        app.state.llm_init_error = f"{type(exc).__name__}: {exc}"
        logger.warning(
            "Platform LLM not available — running in BYOK-only mode: %s: %s",
            type(exc).__name__, exc,
        )
    # Keep router_health if create_app() already populated it (non-serverless path).
    if not hasattr(app.state, "router_health"):
        app.state.router_health = []
    logger.info(
        "AlphaCore init (lazy): provider=%s platform_llm=%s",
        settings.llm_provider, "ok" if app.state.llm else "absent (BYOK-only)",
    )


async def _run_startup_healthcheck(app: FastAPI) -> None:
    """Fail-fast boot check: the configured LLM provider must be reachable.

    Disabled by LLM_STARTUP_HEALTHCHECK=false (dev/offline scenarios).
    See REFACTOR_PLAN.md §3.4 and feedback_silent_trycatch_antipattern.md.
    """
    settings = app.state.settings
    if not settings.llm_startup_healthcheck:
        logger.info("startup healthcheck: skipped (LLM_STARTUP_HEALTHCHECK=false)")
        return
    llm = app.state.llm
    if llm is None:
        # Phase 1 BYOK — no platform LLM is a valid deploy state. The
        # per-request `byok.get_llm_client` dependency handles auth.
        logger.info(
            "startup healthcheck: skipped (BYOK-only mode, platform LLM absent)"
        )
        return
    try:
        ok = await llm.is_available()
    except Exception as exc:
        raise ProviderUnavailableError(
            f"LLM provider {settings.llm_provider!r} health check raised: "
            f"{type(exc).__name__}: {exc}"
        ) from exc
    if not ok:
        raise ProviderUnavailableError(
            f"LLM provider {settings.llm_provider!r} is unreachable. "
            "Set LLM_STARTUP_HEALTHCHECK=false to bypass for dev."
        )
    logger.info("startup healthcheck: %s reachable", settings.llm_provider)


# ── Lifespan (used by uvicorn, may be skipped on Vercel) ──────────────────

@asynccontextmanager
async def _lifespan(application: FastAPI) -> AsyncIterator[None]:
    _ensure_initialized(application)
    await _run_startup_healthcheck(application)
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
        # Phase 1 BYOK — explicit allowlist of the X-LLM-* headers the
        # browser needs to send. The "*" wildcard works in Chromium but
        # Safari has historically been finicky with custom headers under
        # CORS preflight; listing them avoids that class of bug.
        allow_headers=[
            "*",
            "Authorization",
            "X-LLM-Provider",
            "X-LLM-API-Key",
            "X-LLM-Base-URL",
            "X-LLM-Model",
        ],
    )

    # Security middleware (skip in serverless — BaseHTTPMiddleware incompatible)
    if not SERVERLESS:
        from alpha_agent.api.security import SecurityMiddleware

        auth_enabled = os.environ.get("ALPHACORE_AUTH_ENABLED", "false").lower() == "true"
        application.add_middleware(SecurityMiddleware, auth_enabled=auth_enabled)

    # Router loading with per-router health tracking.
    # Silent ImportError is the root cause of ghost-route bugs (see
    # feedback_silent_trycatch_antipattern.md). We track every attempt and
    # surface it at /healthz/routers so curl can prove what actually loaded.
    router_health: list[RouterHealth] = getattr(
        application.state, "router_health", []
    )

    def _load(name: str, loader) -> None:
        try:
            application.include_router(loader())
            router_health.append(RouterHealth(name=name, loaded=True))
        except Exception as exc:  # noqa: BLE001 — report every reason
            router_health.append(
                RouterHealth(
                    name=name,
                    loaded=False,
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
            logger.error("router %s failed to load: %s: %s", name, type(exc).__name__, exc)

    def _import_system():
        from alpha_agent.api.routes.system import router
        return router

    def _import_serverless():
        from alpha_agent.api.routes.serverless import router
        return router

    def _import_interactive():
        from alpha_agent.api.routes.interactive import router
        return router

    def _import_data():
        from alpha_agent.api.routes.data import router
        return router

    def _import_signal():
        from alpha_agent.api.routes.signal import router
        return router

    def _import_screener():
        from alpha_agent.api.routes.screener import router
        return router

    def _import_factors_db():
        from alpha_agent.api.routes.factors_db import router
        return router

    def _import_zoo():
        from alpha_agent.api.routes.zoo import router
        return router

    _load("system", _import_system)
    _load("serverless", _import_serverless)
    _load("interactive", _import_interactive)
    _load("data", _import_data)
    _load("signal", _import_signal)
    _load("screener", _import_screener)
    _load("zoo", _import_zoo)
    _load("factors_db", _import_factors_db)

    if not SERVERLESS:
        def _import_websocket():
            from alpha_agent.api.websocket import router
            return router

        _load("websocket", _import_websocket)

    application.state.router_health = router_health

    @application.get("/api/health")
    async def health() -> dict:
        return {"status": "ok", "service": "alphacore", "mode": "serverless" if SERVERLESS else "full"}

    @application.get("/healthz/routers", response_model=list[RouterHealth])
    async def healthz_routers() -> list[RouterHealth]:
        """Return per-router load status. Curl this to prove what is mounted."""
        return getattr(application.state, "router_health", [])

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
