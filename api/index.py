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


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "service": "alphacore", "mode": "serverless"}


print(f"App ready: {len(app.routes)} routes", file=sys.stderr, flush=True)
