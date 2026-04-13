"""Vercel serverless entry point — exports the FastAPI app."""

import sys
import traceback

try:
    from alpha_agent.api.app import app  # noqa: F401
    print(f"APP LOADED OK: routes={len(app.routes)}", file=sys.stderr, flush=True)
except Exception:
    # Fallback: create a minimal app so we can see the error
    print(f"IMPORT ERROR:\n{traceback.format_exc()}", file=sys.stderr, flush=True)
    from fastapi import FastAPI
    app = FastAPI()

    @app.get("/api/health")
    async def health():
        return {"status": "error", "detail": "App failed to load — check runtime logs"}

    @app.get("/api/debug")
    async def debug():
        return {
            "python": sys.version,
            "path": sys.path,
            "error": traceback.format_exc(),
        }
