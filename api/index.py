"""Vercel serverless entry point — full app with error capture."""

import sys
import traceback

try:
    from alpha_agent.api.app import app  # noqa: F401
except Exception:
    # If app fails to load, create diagnostic fallback
    from fastapi import FastAPI
    app = FastAPI()
    _err = traceback.format_exc()
    print(f"APP LOAD ERROR:\n{_err}", file=sys.stderr, flush=True)

    @app.get("/api/health")
    async def health():
        return {"status": "error", "error": _err}
