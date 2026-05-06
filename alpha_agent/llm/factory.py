"""LLM client factory — creates the right client based on config.

Default path constructs `LiteLLMClient` (A1) for all three providers via
LiteLLM's unified `acompletion`. Provider differences (api_base, model
prefix, custom UA for Kimi) are encoded here in the dispatch — the
LiteLLMClient itself is provider-agnostic.

Kill switch: set `LLM_USE_LEGACY=1` to fall back to the hand-rolled httpx
clients in `_legacy/`. Kept for one release cycle so any provider regression
in LiteLLM's Anthropic-compat handling has an immediate-revert path
without a redeploy.
"""
from __future__ import annotations

import os

from alpha_agent.config import Settings
from alpha_agent.llm.base import LLMClient
from alpha_agent.llm.litellm_client import LiteLLMClient


# Kimi For Coding's `/messages` endpoint allow-lists known coding agents
# by User-Agent. claude-cli is one of the allow-listed UAs.
_KIMI_USER_AGENT = "claude-cli/1.0.0 (external, cli)"
_KIMI_ANTHROPIC_VERSION = "2023-06-01"


def create_llm_client(settings: Settings) -> LLMClient:
    """Create an LLM client based on the configured provider.

    Reads LLM_PROVIDER from .env:
        "ollama" -> LiteLLMClient routing to Ollama (local / AutoDL)
        "openai" -> LiteLLMClient routing to OpenAI / Azure / vLLM proxy
        "kimi"   -> LiteLLMClient routing to Kimi For Coding via Anthropic-compat

    Set LLM_USE_LEGACY=1 to instead use the hand-rolled httpx clients in
    `_legacy/` — kept as a kill switch in case a LiteLLM regression breaks
    a provider's response shape mid-release.
    """
    if os.environ.get("LLM_USE_LEGACY") == "1":
        return _create_legacy_client(settings)

    match settings.llm_provider:
        case "ollama":
            return LiteLLMClient(
                model=f"ollama/{settings.ollama_model}",
                api_base=settings.ollama_base_url,
                api_key=None,  # Ollama doesn't require auth
                # Gemma4 thinking models occasionally drop the answer into a
                # thinking field rather than content. Mirror legacy behavior.
                thinking_fallback=True,
            )
        case "openai":
            if not settings.openai_api_key:
                raise ValueError(
                    "OPENAI_API_KEY is required when LLM_PROVIDER=openai. "
                    "Set it in your .env file."
                )
            return LiteLLMClient(
                model=f"openai/{settings.openai_model}",
                api_key=settings.openai_api_key,
                api_base=settings.openai_base_url,
            )
        case "kimi":
            if not settings.kimi_api_key:
                raise ValueError(
                    "KIMI_API_KEY is required when LLM_PROVIDER=kimi. "
                    "Get one at https://platform.moonshot.cn/console/api-keys "
                    "(sk-kimi-* keys are for Kimi For Coding)."
                )
            # Kimi For Coding uses Anthropic-compat /messages at a custom base.
            # LiteLLM's "anthropic/" prefix surfaces x-api-key + anthropic-version
            # automatically; we pass the UA via extra_headers because Kimi
            # gates on it.
            return LiteLLMClient(
                model=f"anthropic/{settings.kimi_model}",
                api_key=settings.kimi_api_key,
                api_base=settings.kimi_base_url,
                extra_headers={
                    "User-Agent": _KIMI_USER_AGENT,
                    "anthropic-version": _KIMI_ANTHROPIC_VERSION,
                },
            )
        case _:
            raise ValueError(
                f"Unknown LLM provider: {settings.llm_provider!r}. "
                "Use 'ollama', 'openai', or 'kimi'."
            )


def _create_legacy_client(settings: Settings) -> LLMClient:
    """Construct a legacy hand-rolled httpx client. Reserved for the
    `LLM_USE_LEGACY=1` kill-switch path. Imports are lazy so the legacy
    code never loads in normal operation."""
    from alpha_agent.llm._legacy.kimi import KimiClient
    from alpha_agent.llm._legacy.ollama import OllamaClient
    from alpha_agent.llm._legacy.openai import OpenAIClient

    match settings.llm_provider:
        case "ollama":
            return OllamaClient(
                base_url=settings.ollama_base_url,
                model=settings.ollama_model,
            )
        case "openai":
            if not settings.openai_api_key:
                raise ValueError("OPENAI_API_KEY is required when LLM_PROVIDER=openai.")
            return OpenAIClient(
                api_key=settings.openai_api_key,
                base_url=settings.openai_base_url,
                model=settings.openai_model,
            )
        case "kimi":
            if not settings.kimi_api_key:
                raise ValueError("KIMI_API_KEY is required when LLM_PROVIDER=kimi.")
            return KimiClient(
                api_key=settings.kimi_api_key,
                base_url=settings.kimi_base_url,
                model=settings.kimi_model,
            )
        case _:
            raise ValueError(f"Unknown LLM provider: {settings.llm_provider!r}")
