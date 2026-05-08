"""GET /api/system — System health monitoring endpoint."""

from __future__ import annotations

import platform
import sys
import time
from pathlib import Path

from fastapi import APIRouter, Request

from alpha_agent.api.cache import TTLCache

router = APIRouter(prefix="/api", tags=["system"])

_START_TIME = time.monotonic()


@router.get("/system")
async def system_health(request: Request) -> dict:
    """Return system health, service status, and model info."""
    cache: TTLCache = request.app.state.cache
    settings = request.app.state.settings

    cached = cache.get("system_health")
    if cached is not None:
        return cached

    # LLM availability check (Phase 1 BYOK aware)
    llm_status = "unknown"
    llm = getattr(request.app.state, "llm", None)
    if llm is None:
        llm_status = "byok"
    else:
        try:
            llm_status = "ok" if await llm.is_available() else "unreachable"
        except Exception:
            llm_status = "error"

    # Model file status (may not exist in serverless)
    try:
        model_dir = Path(settings.model_dir)
        joblib_files = list(model_dir.glob("*.joblib")) if model_dir.exists() else []
        models_trained = len(joblib_files) > 0
        last_trained = (
            max(f.stat().st_mtime for f in joblib_files) if joblib_files else None
        )
    except (OSError, PermissionError):
        joblib_files = []
        models_trained = False
        last_trained = None

    result = {
        "services": {
            "llm": llm_status,
            "fastapi": "ok",
            "tunnel": "unknown",
        },
        "models": {
            "trained": models_trained,
            "last_trained": last_trained,
            "model_files": [f.name for f in joblib_files],
        },
        "system": {
            "uptime_seconds": round(time.monotonic() - _START_TIME, 1),
            "python_version": sys.version,
            "platform": platform.platform(),
        },
        "cache_stats": {"ttl_seconds": settings.dashboard_cache_ttl_seconds},
    }

    cache.set("system_health", result, settings.dashboard_cache_ttl_seconds)
    return result
