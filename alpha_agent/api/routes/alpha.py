"""GET /api/alpha — Alpha strategy lab endpoint."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Request

from alpha_agent.api.cache import TTLCache
from alpha_agent.pipeline.registry import FactorRegistry

router = APIRouter(prefix="/api", tags=["alpha"])


@router.get("/alpha")
async def alpha_lab(request: Request) -> dict:
    """Return registered factors and pipeline status."""
    cache: TTLCache = request.app.state.cache
    settings = request.app.state.settings

    cached = cache.get("alpha_lab")
    if cached is not None:
        return cached

    # Load factors from SQLite registry (may not exist yet)
    factors: list[dict] = []
    try:
        registry = FactorRegistry()
        records = registry.list_all()
        factors = [asdict(r) for r in records]
    except Exception:
        factors = []

    result = {
        "factors": factors,
        "pipeline_status": {
            "available": True,
            "max_iterations": settings.max_iterations,
        },
    }

    cache.set("alpha_lab", result, settings.dashboard_cache_ttl_seconds)
    return result
