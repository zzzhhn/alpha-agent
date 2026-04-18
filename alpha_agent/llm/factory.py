"""LLM client factory — creates the right client based on config."""

from __future__ import annotations

from alpha_agent.config import Settings
from alpha_agent.llm.base import LLMClient
from alpha_agent.llm.kimi import KimiClient
from alpha_agent.llm.ollama import OllamaClient
from alpha_agent.llm.openai import OpenAIClient


def create_llm_client(settings: Settings) -> LLMClient:
    """Create an LLM client based on the configured provider.

    Reads LLM_PROVIDER from .env:
        "ollama" -> OllamaClient (local / AutoDL)
        "openai" -> OpenAIClient (generic OpenAI-compatible API)
        "kimi"   -> KimiClient (Anthropic-compat /messages at api.kimi.com/coding/v1)
    """
    match settings.llm_provider:
        case "ollama":
            return OllamaClient(
                base_url=settings.ollama_base_url,
                model=settings.ollama_model,
            )
        case "openai":
            if not settings.openai_api_key:
                raise ValueError(
                    "OPENAI_API_KEY is required when LLM_PROVIDER=openai. "
                    "Set it in your .env file."
                )
            return OpenAIClient(
                api_key=settings.openai_api_key,
                base_url=settings.openai_base_url,
                model=settings.openai_model,
            )
        case "kimi":
            if not settings.kimi_api_key:
                raise ValueError(
                    "KIMI_API_KEY is required when LLM_PROVIDER=kimi. "
                    "Get one at https://platform.moonshot.cn/console/api-keys "
                    "(sk-kimi-* keys are for Kimi For Coding)."
                )
            return KimiClient(
                api_key=settings.kimi_api_key,
                base_url=settings.kimi_base_url,
                model=settings.kimi_model,
            )
        case _:
            raise ValueError(
                f"Unknown LLM provider: {settings.llm_provider!r}. "
                "Use 'ollama', 'openai', or 'kimi'."
            )
