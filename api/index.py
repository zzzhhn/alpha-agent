"""Vercel serverless entry point: builds a lightweight FastAPI app directly.

Bypasses alpha_agent.api.app.create_app() which has compatibility issues
with Vercel's Python runtime. Router registration goes through a uniform
_load(name, modpath) helper that records every attempt (loaded vs failed)
in app.state.router_health. The /api/_health/routers endpoint surfaces
that list so a silently-missing router is curl-visible, not buried in
stderr only. Without the manifest, an ImportError in any one router is
swallowed by per-block try/except and the deploy still goes READY with
that route 404ing forever.
"""

import importlib
import os
import sys
import traceback

os.environ.setdefault("SERVERLESS", "true")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from alpha_agent.core.types import RouterHealth

app = FastAPI(title="AlphaCore Dashboard API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*", "Authorization"],
)

# ── app.state init ──────────────────────────────────────────────────────
app.state.router_health = []
# Backward-compat dict for the legacy /api/_debug/load-errors endpoint.
_m2_load_errors: dict[str, str] = {}

try:
    from alpha_agent.config import get_settings
    from alpha_agent.api.cache import TTLCache

    settings = get_settings()
    app.state.settings = settings
    app.state.cache = TTLCache()

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
    print(f"✗ Settings init failed: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
    traceback.print_exc(file=sys.stderr)
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


# ── Router registration via uniform _load helper ────────────────────────
# Every router that the lambda should serve is enumerated below. _load
# tracks every attempt in app.state.router_health (loaded=True/False
# + the error text on failure), so /api/_health/routers shows BOTH what
# loaded AND what silently dropped. Without this manifest, the per-block
# try/except hides ImportError as a 404 forever (the watchlist trap of
# 2026-05-15: the router code shipped, but its name was never enumerated
# here, so it was simply absent from the lambda).
def _load(name: str, modpath: str) -> None:
    try:
        router = importlib.import_module(modpath).router
        app.include_router(router)
        app.state.router_health.append(RouterHealth(name=name, loaded=True))
        print(f"✓ {name} routes loaded", file=sys.stderr, flush=True)
    except Exception as exc:
        err = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
        app.state.router_health.append(
            RouterHealth(name=name, loaded=False, error=err[:1500])
        )
        _m2_load_errors[name] = err
        print(f"✗ {name} routes: {err}", file=sys.stderr, flush=True)


_load("serverless",   "alpha_agent.api.routes.serverless")
_load("system",       "alpha_agent.api.routes.system")
_load("interactive",  "alpha_agent.api.routes.interactive")
_load("data",         "alpha_agent.api.routes.data")
_load("signal",       "alpha_agent.api.routes.signal")
_load("screener",     "alpha_agent.api.routes.screener")
_load("zoo",          "alpha_agent.api.routes.zoo")
_load("picks",        "alpha_agent.api.routes.picks")
_load("basket_edge",  "alpha_agent.api.routes.basket_edge")
_load("stock",        "alpha_agent.api.routes.stock")
_load("brief",        "alpha_agent.api.routes.brief")
_load("watchlist",    "alpha_agent.api.routes.watchlist")
_load("m2_health",    "alpha_agent.api.routes.health")
_load("cron_routes",  "alpha_agent.api.routes.cron_routes")
_load("admin",        "alpha_agent.api.routes.admin")
_load("alerts",       "alpha_agent.api.routes.alerts")
_load("user",         "alpha_agent.api.routes.user")
_load("macro_context", "alpha_agent.api.routes.macro_context")
_load("news_enrich",   "alpha_agent.api.routes.news_enrich")
_load("ic_backtest",   "alpha_agent.api.routes.ic_backtest")
_load("evolution",     "alpha_agent.api.routes.evolution")
_load("factor_lab",    "alpha_agent.api.routes.factor_lab")
_load("brain",         "alpha_agent.api.routes.brain_routes")

# Probe asyncpg directly so we know it's installed in the runtime.
try:
    import asyncpg  # noqa: F401
    _m2_load_errors["_asyncpg_import"] = "OK"
except Exception as e:
    _m2_load_errors["_asyncpg_import"] = f"{type(e).__name__}: {e}"

app.state.m2_load_errors = _m2_load_errors

# Phase 3a: load the AST whitelist union (built-ins + extended_operators) at
# cold start so newly approved operators are accepted by the validator from
# request 0. Surface any failure via app.state.allowed_ops_refresh_error so
# /api/healthz/ast can report it (silent-exception anti-pattern: a missed
# refresh would silently reject any non-builtin operator with no signal).
try:
    import asyncio
    _db_url = os.environ.get("DATABASE_URL")
    if _db_url:
        from alpha_agent.core.factor_ast import refresh_allowed_ops
        asyncio.run(refresh_allowed_ops(_db_url))
        app.state.allowed_ops_refresh_error = None
        print("✓ AST whitelist union loaded", file=sys.stderr, flush=True)
    else:
        app.state.allowed_ops_refresh_error = "no DATABASE_URL: whitelist is builtin-only"
except Exception as e:
    app.state.allowed_ops_refresh_error = f"{type(e).__name__}: {e}"
    print(f"⚠ AST whitelist refresh failed: {app.state.allowed_ops_refresh_error}",
          file=sys.stderr, flush=True)


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "service": "alphacore", "mode": "serverless"}


@app.get("/api/healthz/ast")
async def healthz_ast() -> dict:
    """Phase 3a: surface the AST whitelist size + any startup-refresh error.
    Duplicated here because api/index.py bypasses create_app() (dual-entry rule)."""
    try:
        from alpha_agent.core.factor_ast import BUILTIN_OPS, get_allowed_ops
        ops = get_allowed_ops()
        return {
            "builtin_ops_count": len(BUILTIN_OPS),
            "allowed_ops_count": len(ops),
            "extended_ops_count": len(ops - BUILTIN_OPS),
            "refresh_error": getattr(app.state, "allowed_ops_refresh_error", None),
        }
    except Exception as exc:  # noqa: BLE001 - surface to the response, not swallow
        return {"error": f"{type(exc).__name__}: {exc}"}


@app.get("/api/healthz/sandbox")
async def healthz_sandbox() -> dict:
    """Phase 3b: SandboxRunner pool health. See create_app() version for docs."""
    runner = getattr(app.state, "sandbox_runner", None)
    if runner is None:
        try:
            from alpha_agent.evolution.sandbox import SandboxRunner
            runner = SandboxRunner()
            app.state.sandbox_runner = runner
            app.state.sandbox_init_error = None
        except Exception as exc:
            app.state.sandbox_init_error = f"{type(exc).__name__}: {exc}"
            return {"init_error": app.state.sandbox_init_error}
    stat = runner.stat()
    stat["init_error"] = getattr(app.state, "sandbox_init_error", None)
    return stat


@app.get("/api/_debug/load-errors")
async def debug_load_errors() -> dict:
    """Surface every router cold-start ImportError + asyncpg probe result.
    Kept for backward compat; prefer /api/_health/routers for the structured
    loaded/failed manifest."""
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
