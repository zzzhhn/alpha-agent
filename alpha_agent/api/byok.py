"""BYOK (Bring Your Own Key) FastAPI dependency.

Open-source self-deploys of alpha-agent must NOT consume the platform
operator's LLM quota. Visitors paste their own provider credentials in
the frontend Settings page; those values flow as request headers and
this module materializes a per-request `LLMClient` from them.

Headers consumed (all case-insensitive, all optional except api_key):
  X-LLM-Provider   = "openai" | "kimi" | "ollama" | "anthropic"  (default: openai)
  X-LLM-API-Key    = the provider key  (required unless platform fallback exists)
  X-LLM-Base-URL   = optional override; e.g. for Ollama tunnels or LiteLLM proxies
  X-LLM-Model      = model id within the provider; provider-specific defaults apply

Resolution order (per request):
  1. If ALL required headers are present → build LiteLLMClient from headers.
  2. Else if `app.state.llm` is set AND `ALPHACORE_REQUIRE_BYOK` is NOT "true"
     → fall back to the platform LLM (development convenience; user has
     `.env` configured locally).
  3. Else → 401 with explicit "BYOK required" message + the header names
     the client should send.

Security notes:
  * The key value is read once per request and only ever passed to
    LiteLLM's `acompletion()`. It is never logged, written to disk,
    cached, or echoed in responses. Code that adds new logging near the
    LLM call path MUST scrub these headers.
  * `app.state.llm` (when present) is the operator's fallback for local
    dev; deploys to public URLs MUST set `ALPHACORE_REQUIRE_BYOK=true`
    so step (2) is disabled.
"""
from __future__ import annotations

import logging
import os
from typing import Literal

from fastapi import Header, HTTPException, Request

from alpha_agent.llm.base import LLMClient
from alpha_agent.llm.litellm_client import LiteLLMClient

logger = logging.getLogger(__name__)


_KIMI_USER_AGENT = "claude-cli/1.0.0 (external, cli)"
_KIMI_ANTHROPIC_VERSION = "2023-06-01"

# Default api_base / model per provider when the BYOK headers omit them.
# These mirror the Settings model defaults in `alpha_agent/config.py` so the
# same provider strings produce identical clients regardless of source.
_PROVIDER_DEFAULTS: dict[str, dict[str, str]] = {
    "openai": {
        "api_base": "https://api.openai.com/v1",
        "model": "gpt-4o",
        "model_prefix": "openai",
    },
    "kimi": {
        "api_base": "https://api.kimi.com/coding/v1",
        "model": "kimi-for-coding",
        "model_prefix": "anthropic",  # Kimi For Coding uses Anthropic-compat
    },
    "ollama": {
        "api_base": "http://localhost:11434",
        "model": "gemma4:26b",
        "model_prefix": "ollama",
    },
    "anthropic": {
        "api_base": "https://api.anthropic.com",
        "model": "claude-sonnet-4-5",
        "model_prefix": "anthropic",
    },
}

_VALID_PROVIDERS = frozenset(_PROVIDER_DEFAULTS.keys())


def _build_byok_client(
    provider: str,
    api_key: str,
    api_base: str | None,
    model: str | None,
) -> LLMClient:
    """Construct a LiteLLMClient from raw header values."""
    if provider not in _VALID_PROVIDERS:
        raise HTTPException(
            400,
            f"Unsupported X-LLM-Provider {provider!r}. "
            f"Valid: {sorted(_VALID_PROVIDERS)}",
        )

    defaults = _PROVIDER_DEFAULTS[provider]
    resolved_base = api_base or defaults["api_base"]
    resolved_model = model or defaults["model"]
    full_model = f"{defaults['model_prefix']}/{resolved_model}"

    extra_headers: dict[str, str] | None = None
    thinking_fallback = False
    if provider == "kimi":
        extra_headers = {
            "User-Agent": _KIMI_USER_AGENT,
            "anthropic-version": _KIMI_ANTHROPIC_VERSION,
        }
    elif provider == "ollama":
        thinking_fallback = True

    return LiteLLMClient(
        model=full_model,
        api_key=api_key,
        api_base=resolved_base,
        extra_headers=extra_headers,
        thinking_fallback=thinking_fallback,
    )


def get_llm_client(
    request: Request,
    x_llm_provider: str | None = Header(default=None),
    x_llm_api_key: str | None = Header(default=None),
    x_llm_base_url: str | None = Header(default=None),
    x_llm_model: str | None = Header(default=None),
) -> LLMClient:
    """FastAPI dependency. Returns a per-request LLM client.

    Use as `llm: LLMClient = Depends(get_llm_client)` in any route handler
    that needs to call `llm.chat()`.
    """
    # Path 1: BYOK headers fully provided.
    if x_llm_api_key:
        provider = (x_llm_provider or "openai").lower()
        return _build_byok_client(
            provider=provider,
            api_key=x_llm_api_key,
            api_base=x_llm_base_url,
            model=x_llm_model,
        )

    # Path 2: fallback to platform LLM if BYOK is not required.
    require_byok = os.environ.get("ALPHACORE_REQUIRE_BYOK", "false").lower() == "true"
    platform_llm = getattr(request.app.state, "llm", None)
    if not require_byok and platform_llm is not None:
        return platform_llm

    # Path 3: hard fail with a useful message.
    raise HTTPException(
        status_code=401,
        detail={
            "error": "byok_required",
            "message": (
                "This deployment requires you to bring your own LLM key. "
                "Send the following headers with your request, or configure "
                "them in the Settings page of the frontend."
            ),
            "required_headers": {
                "X-LLM-Provider": "one of: openai, kimi, ollama, anthropic",
                "X-LLM-API-Key": "your provider API key",
            },
            "optional_headers": {
                "X-LLM-Base-URL": "override the provider's default endpoint",
                "X-LLM-Model": "override the provider's default model id",
            },
        },
    )
