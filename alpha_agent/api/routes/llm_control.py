"""LLM provider control endpoints — runtime switching without .env writes."""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from alpha_agent.config import get_settings
from alpha_agent.llm.base import LLMClient
from alpha_agent.llm.factory import create_llm_client
from alpha_agent.llm.ollama import OllamaClient
from alpha_agent.llm.openai import OpenAIClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/llm", tags=["llm"])

# ---------------------------------------------------------------------------
# In-memory runtime state
# Holds the active provider name and the live client instance.
# Initialised lazily on first use so module import is side-effect-free.
# ---------------------------------------------------------------------------

_runtime: dict = {
    "provider": None,   # str | None — set on first request
    "client": None,     # LLMClient | None
}


def _display_model_name(provider: str, settings) -> str:
    """Return a human-readable model label for the given provider."""
    if provider == "ollama":
        return "Gemma 4 (27B)"
    # For OpenAI-compatible providers, surface the configured model string.
    return settings.openai_model


def _ensure_initialised() -> None:
    """Populate _runtime from settings if it has not been set yet."""
    if _runtime["provider"] is None:
        settings = get_settings()
        _runtime["provider"] = settings.llm_provider
        _runtime["client"] = create_llm_client(settings)
        logger.info("llm_control: initialised with provider=%s", _runtime["provider"])


def get_active_llm_client() -> LLMClient:
    """Return the currently active LLM client.

    Import and call this from any module that needs the runtime-switched client
    instead of the boot-time client stored on app.state.
    """
    _ensure_initialised()
    client = _runtime["client"]
    if client is None:
        raise RuntimeError("LLM client is not initialised")
    return client


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class SwitchRequest(BaseModel):
    provider: Literal["ollama", "openai"]


class LLMStatusResponse(BaseModel):
    provider: str
    model: str
    available: bool


class SwitchResponse(BaseModel):
    provider: str
    model: str
    message: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/status", response_model=LLMStatusResponse, summary="Get current LLM provider status")
async def get_llm_status() -> LLMStatusResponse:
    """Return the active provider, model display name, and live reachability."""
    _ensure_initialised()
    settings = get_settings()
    provider = _runtime["provider"]
    client = _runtime["client"]

    available = False
    if client is not None:
        try:
            available = await client.is_available()
        except Exception as exc:
            logger.warning("llm_control: is_available() raised %s", exc)

    return LLMStatusResponse(
        provider=provider,
        model=_display_model_name(provider, settings),
        available=available,
    )


@router.post("/switch", response_model=SwitchResponse, summary="Switch the active LLM provider at runtime")
async def switch_llm_provider(body: SwitchRequest) -> SwitchResponse:
    """Switch to the requested provider after verifying it is reachable.

    Updates the in-memory state only — the .env file is never modified.
    The new client will be used by get_active_llm_client() from this point on.
    """
    _ensure_initialised()
    settings = get_settings()
    target = body.provider

    # Build a candidate client to probe availability before committing.
    try:
        candidate = create_llm_client(
            # create_llm_client reads provider from settings; build a patched copy.
            _patched_settings(settings, target)
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        reachable = await candidate.is_available()
    except Exception as exc:
        logger.warning("llm_control: availability probe failed for %s: %s", target, exc)
        reachable = False

    if not reachable:
        # Clean up the candidate client's HTTP connection pool.
        if hasattr(candidate, "close"):
            try:
                await candidate.close()
            except Exception:
                pass
        raise HTTPException(
            status_code=503,
            detail=f"Provider '{target}' is not reachable. Switch aborted.",
        )

    # Close the old client before replacing it.
    old_client = _runtime["client"]
    if old_client is not None and hasattr(old_client, "close"):
        try:
            await old_client.close()
        except Exception as exc:
            logger.warning("llm_control: error closing previous client: %s", exc)

    _runtime["provider"] = target
    _runtime["client"] = candidate

    model_label = _display_model_name(target, settings)
    logger.info("llm_control: switched to provider=%s model=%s", target, model_label)

    return SwitchResponse(
        provider=target,
        model=model_label,
        message=f"Switched to {target} ({model_label}) successfully.",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _patched_settings(base_settings, provider: str):
    """Return a copy of settings with llm_provider overridden.

    We construct a plain namespace object rather than mutating the pydantic
    model, keeping all other config values intact.
    """

    class _PatchedSettings:
        llm_provider = provider
        ollama_base_url = base_settings.ollama_base_url
        ollama_model = base_settings.ollama_model
        openai_api_key = base_settings.openai_api_key
        openai_base_url = base_settings.openai_base_url
        openai_model = base_settings.openai_model

    return _PatchedSettings()
