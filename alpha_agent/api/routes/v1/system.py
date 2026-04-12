"""v1 System endpoints — health check and configuration."""

from __future__ import annotations

import platform
import sys
import time
from pathlib import Path

from fastapi import APIRouter, Request

from alpha_agent.api.cache import TTLCache
from alpha_agent.api.routes.v1.schemas import (
    SystemConfigResponse,
    SystemHealthResponse,
)
router = APIRouter(prefix="/system", tags=["system"])

_START_TIME = time.monotonic()


@router.get("/health", response_model=SystemHealthResponse)
async def system_health(request: Request) -> SystemHealthResponse:
    """Return system health, service status, and model info."""
    cache: TTLCache = request.app.state.cache
    settings = request.app.state.settings

    cached = cache.get("v1_system_health")
    if cached is not None:
        return cached

    llm_status = "unknown"
    try:
        llm = request.app.state.llm
        llm_status = "ok" if await llm.is_available() else "unreachable"
    except Exception:
        llm_status = "error"

    model_dir = Path(settings.model_dir)
    joblib_files = (
        list(model_dir.glob("*.joblib")) if model_dir.exists() else []
    )
    models_trained = len(joblib_files) > 0
    last_trained = (
        max(f.stat().st_mtime for f in joblib_files) if joblib_files else None
    )

    result = SystemHealthResponse(
        services={
            "llm": llm_status,
            "fastapi": "ok",
            "tunnel": "unknown",
        },
        models={
            "trained": models_trained,
            "last_trained": last_trained,
            "model_files": [f.name for f in joblib_files],
        },
        system={
            "uptime_seconds": round(time.monotonic() - _START_TIME, 1),
            "python_version": sys.version,
            "platform": platform.platform(),
        },
        cache_stats={"ttl_seconds": settings.dashboard_cache_ttl_seconds},
    )

    cache.set(
        "v1_system_health", result, settings.dashboard_cache_ttl_seconds
    )
    return result


@router.get("/config", response_model=SystemConfigResponse)
async def system_config(request: Request) -> SystemConfigResponse:
    """Return non-secret system configuration."""
    settings = request.app.state.settings

    return SystemConfigResponse(
        tickers=settings.dashboard_tickers,
        cache_ttl_seconds=settings.dashboard_cache_ttl_seconds,
        fastapi_port=settings.fastapi_port,
        llm_provider=settings.llm_provider,
        ollama_model=settings.ollama_model,
        max_iterations=settings.max_iterations,
        data_cache_max_age_hours=settings.data_cache_max_age_hours,
    )
