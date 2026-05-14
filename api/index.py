"""Vercel serverless entry point — builds a lightweight FastAPI app directly.

Bypasses alpha_agent.api.app.create_app() which has compatibility issues
with Vercel's Python runtime. Instead, we construct a minimal app here
with only the dependencies needed for serverless mode.
"""

import os
import sys

os.environ.setdefault("SERVERLESS", "true")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="AlphaCore Dashboard API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*", "Authorization"],
)

# ── Initialize app.state ────────────────────────────────────────────────
try:
    from alpha_agent.config import get_settings
    from alpha_agent.api.cache import TTLCache

    settings = get_settings()
    app.state.settings = settings
    app.state.cache = TTLCache()

    # Try to create LLM client (may fail if API key missing etc.)
    try:
        from alpha_agent.llm.factory import create_llm_client
        app.state.llm = create_llm_client(settings)
        app.state.llm_init_error = None
        print(f"✓ LLM init: {settings.llm_provider}", file=sys.stderr, flush=True)
    except Exception as e:
        app.state.llm = None
        app.state.llm_init_error = f"{type(e).__name__}: {e}"
        print(f"⚠ LLM init failed: {app.state.llm_init_error}", file=sys.stderr, flush=True)

except Exception as e:
    import traceback
    print(f"✗ Settings init failed: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
    traceback.print_exc(file=sys.stderr)
    # Bare minimum so routes don't crash on missing state
    # Create a minimal settings-like object with defaults
    from types import SimpleNamespace
    app.state.settings = SimpleNamespace(
        dashboard_tickers=["NVDA", "AAPL", "TSLA"],
        dashboard_cache_ttl_seconds=300,
        llm_provider="openai",
        max_iterations=3,
        data_cache_max_age_hours=24,
    )
    app.state.cache = None
    app.state.llm = None
    app.state.llm_init_error = f"settings_init_failed: {type(e).__name__}: {e}"

# ── Register routes ─────────────────────────────────────────────────────
try:
    from alpha_agent.api.routes.serverless import router as serverless_router
    app.include_router(serverless_router)
    print(f"✓ serverless routes loaded", file=sys.stderr, flush=True)
except Exception as e:
    print(f"✗ serverless routes: {e}", file=sys.stderr, flush=True)

try:
    from alpha_agent.api.routes.system import router as system_router
    app.include_router(system_router)
    print(f"✓ system routes loaded", file=sys.stderr, flush=True)
except Exception as e:
    print(f"✗ system routes: {e}", file=sys.stderr, flush=True)

try:
    from alpha_agent.api.routes.interactive import router as interactive_router
    app.include_router(interactive_router)
    print(f"✓ interactive routes loaded", file=sys.stderr, flush=True)
except Exception as e:
    import traceback
    print(f"✗ interactive routes: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
    traceback.print_exc(file=sys.stderr)

try:
    from alpha_agent.api.routes.data import router as data_router
    app.include_router(data_router)
    print(f"✓ data routes loaded", file=sys.stderr, flush=True)
except Exception as e:
    import traceback
    print(f"✗ data routes: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
    traceback.print_exc(file=sys.stderr)

try:
    from alpha_agent.api.routes.signal import router as signal_router
    app.include_router(signal_router)
    print(f"✓ signal routes loaded", file=sys.stderr, flush=True)
except Exception as e:
    import traceback
    print(f"✗ signal routes: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
    traceback.print_exc(file=sys.stderr)

try:
    from alpha_agent.api.routes.screener import router as screener_router
    app.include_router(screener_router)
    print(f"✓ screener routes loaded", file=sys.stderr, flush=True)
except Exception as e:
    import traceback
    print(f"✗ screener routes: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
    traceback.print_exc(file=sys.stderr)

try:
    from alpha_agent.api.routes.zoo import router as zoo_router
    app.include_router(zoo_router)
    print(f"✓ zoo routes loaded", file=sys.stderr, flush=True)
except Exception as e:
    import traceback
    print(f"✗ zoo routes: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
    traceback.print_exc(file=sys.stderr)

# ── M2 routers ─────────────────────────────────────────────────────────
# Capture import errors into app.state so /api/_debug/load-errors can surface them.
_m2_load_errors: dict[str, str] = {}

try:
    from alpha_agent.api.routes.picks import router as picks_router
    app.include_router(picks_router)
    print(f"✓ picks routes loaded", file=sys.stderr, flush=True)
except Exception as e:
    import traceback
    msg = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
    _m2_load_errors["picks"] = msg
    print(f"✗ picks routes: {msg}", file=sys.stderr, flush=True)

try:
    from alpha_agent.api.routes.stock import router as stock_router
    app.include_router(stock_router)
    print(f"✓ stock routes loaded", file=sys.stderr, flush=True)
except Exception as e:
    import traceback
    msg = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
    _m2_load_errors["stock"] = msg
    print(f"✗ stock routes: {msg}", file=sys.stderr, flush=True)

try:
    from alpha_agent.api.routes.brief import router as brief_router
    app.include_router(brief_router)
    print(f"✓ brief routes loaded", file=sys.stderr, flush=True)
except Exception as e:
    import traceback
    msg = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
    _m2_load_errors["brief"] = msg
    print(f"✗ brief routes: {msg}", file=sys.stderr, flush=True)

try:
    from alpha_agent.api.routes.health import router as m2_health_router
    app.include_router(m2_health_router)
    print(f"✓ M2 health routes loaded", file=sys.stderr, flush=True)
except Exception as e:
    import traceback
    msg = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
    _m2_load_errors["m2_health"] = msg
    print(f"✗ M2 health routes: {msg}", file=sys.stderr, flush=True)

# Probe asyncpg directly so we know if it's installed in the runtime
try:
    import asyncpg  # noqa: F401
    _m2_load_errors["_asyncpg_import"] = "OK"
except Exception as e:
    _m2_load_errors["_asyncpg_import"] = f"{type(e).__name__}: {e}"

app.state.m2_load_errors = _m2_load_errors

try:
    from alpha_agent.api.routes.cron_routes import router as cron_router
    app.include_router(cron_router)
    print(f"✓ cron routes loaded", file=sys.stderr, flush=True)
except Exception as e:
    import traceback
    print(f"✗ cron routes: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
    traceback.print_exc(file=sys.stderr)

try:
    from alpha_agent.api.routes.admin import router as admin_router
    app.include_router(admin_router)
    print(f"✓ admin routes loaded", file=sys.stderr, flush=True)
except Exception as e:
    import traceback
    msg = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
    _m2_load_errors["admin"] = msg
    print(f"✗ admin routes: {msg}", file=sys.stderr, flush=True)

try:
    from alpha_agent.api.routes.alerts import router as alerts_router
    app.include_router(alerts_router)
    print(f"✓ alerts routes loaded", file=sys.stderr, flush=True)
except Exception as e:
    import traceback
    msg = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
    _m2_load_errors["alerts"] = msg
    print(f"✗ alerts routes: {msg}", file=sys.stderr, flush=True)

try:
    from alpha_agent.api.routes.user import router as user_router
    app.include_router(user_router)
    print(f"✓ user routes loaded", file=sys.stderr, flush=True)
except Exception as e:
    import traceback
    msg = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
    _m2_load_errors["user"] = msg
    print(f"✗ user routes: {msg}", file=sys.stderr, flush=True)


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "service": "alphacore", "mode": "serverless"}


@app.get("/api/_debug/load-errors")
async def debug_load_errors() -> dict:
    """Surface every M2 router cold-start ImportError + asyncpg probe result."""
    return getattr(app.state, "m2_load_errors", {})


@app.get("/api/_debug/routes")
async def debug_routes() -> dict:
    """List every mounted route so we can see what survived cold-start imports."""
    routes = []
    for r in app.routes:
        path = getattr(r, "path", None)
        methods = sorted(getattr(r, "methods", set()) - {"HEAD"})
        if path and methods:
            routes.append({"path": path, "methods": methods})
    routes.sort(key=lambda x: x["path"])
    return {"total": len(routes), "routes": routes}


print(f"App ready: {len(app.routes)} routes", file=sys.stderr, flush=True)
