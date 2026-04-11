"""GET /api/system — System health monitoring endpoint."""

from __future__ import annotations

import platform
import sys
import time
from pathlib import Path

from fastapi import APIRouter, Request

from alpha_agent.api.cache import TTLCache
from alpha_agent.llm.ollama import OllamaClient

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

    # Ollama availability check
    ollama_status = "unknown"
    try:
        client = OllamaClient(base_url=settings.ollama_base_url)
        ollama_status = "ok" if await client.is_available() else "unreachable"
        await client.close()
    except Exception:
        ollama_status = "error"

    # Model file status
    model_dir = Path(settings.model_dir)
    joblib_files = list(model_dir.glob("*.joblib")) if model_dir.exists() else []
    models_trained = len(joblib_files) > 0
    last_trained = (
        max(f.stat().st_mtime for f in joblib_files) if joblib_files else None
    )

    result = {
        "services": {
            "ollama": ollama_status,
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
