"""Unified LiteLLM-based LLM client (A1).

Replaces three hand-rolled httpx clients (`openai.py`, `kimi.py`, `ollama.py`,
~280 LOC of duplicated retry / token-counting / availability-probing logic)
with a single LiteLLM-routed call. LiteLLM handles:

  * provider-specific request/response shapes (OpenAI chat-completions vs
    Anthropic /messages vs Ollama /api/chat)
  * standard 429/5xx retry with exponential backoff
  * token-usage extraction across providers
  * streaming (we don't use it, but it's there)

Why one class instead of three thin LiteLLM-wrapping subclasses:
  * The provider-specific knobs (api_base, extra_headers, model prefix)
    are all init kwargs in LiteLLM; subclasses would be 5-line constructors
    each, no behavioral specialization
  * The factory (`factory.py`) already encodes per-provider configuration —
    keeping the dispatch there makes one source of truth for "which knob
    each provider needs"

Edge cases preserved from the legacy clients:
  * Ollama / gemma4-thinking responses sometimes leave `content=""` and
    embed the answer inside a `thinking` field. We replicate the legacy
    JSON-block extraction so existing tests + production traffic see the
    same response shape.
  * Kimi For Coding's `/messages` endpoint requires `User-Agent: claude-cli/*`
    (UA-gated allow-list). We pass it via `extra_headers`.

Legacy clients moved to `alpha_agent/llm/_legacy/` and reachable via
`LLM_USE_LEGACY=1` env var as a kill switch — see `factory.py`.
"""
from __future__ import annotations

import logging
import re

import litellm

from alpha_agent.llm.base import LLMClient, LLMResponse, Message

logger = logging.getLogger(__name__)


class LiteLLMClient(LLMClient):
    """Talks to any provider LiteLLM supports via the unified `acompletion` API.

    Construction:
      model:        LiteLLM-prefixed model id (e.g. "openai/gpt-4o",
                    "ollama/gemma4:26b", "anthropic/kimi-for-coding")
      api_key:      provider API key, or None if not required (Ollama)
      api_base:     custom base URL, or None for provider default
      extra_headers: dict merged into outgoing HTTP headers (used for Kimi UA)
      thinking_fallback: when True, on empty `content` we extract from
                    response.choices[0].message.reasoning_content (if any)
                    using legacy gemma4 JSON-block heuristics

    Construct via `factory.create_llm_client` rather than instantiating
    directly; the factory encodes each provider's correct kwargs.
    """

    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        api_base: str | None = None,
        extra_headers: dict[str, str] | None = None,
        thinking_fallback: bool = False,
        timeout: float = 120.0,
    ) -> None:
        self._model = model
        self._api_key = api_key
        self._api_base = api_base
        self._extra_headers = dict(extra_headers) if extra_headers else None
        self._thinking_fallback = thinking_fallback
        self._timeout = timeout

    def _kwargs(self) -> dict[str, object]:
        kw: dict[str, object] = {"model": self._model, "timeout": self._timeout}
        if self._api_key is not None:
            kw["api_key"] = self._api_key
        if self._api_base is not None:
            kw["api_base"] = self._api_base
        if self._extra_headers is not None:
            kw["extra_headers"] = self._extra_headers
        return kw

    async def chat(
        self,
        messages: list[Message],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        payload_messages = [{"role": m.role, "content": m.content} for m in messages]
        response = await litellm.acompletion(
            messages=payload_messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **self._kwargs(),
        )

        choice = response.choices[0]
        content = (choice.message.content or "")

        if not content.strip() and self._thinking_fallback:
            # Gemma4-style thinking models occasionally emit the answer inside
            # a thinking / reasoning_content field. Try both attribute names
            # since LiteLLM has shifted between them across versions.
            thinking = (
                getattr(choice.message, "reasoning_content", None)
                or getattr(choice.message, "thinking", None)
                or ""
            )
            if thinking:
                content = _extract_from_thinking(thinking)

        usage = getattr(response, "usage", None)
        prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0) if usage else 0
        completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0) if usage else 0

        return LLMResponse(
            content=content,
            model=getattr(response, "model", self._model) or self._model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

    async def is_available(self) -> bool:
        """Smoke-test the configured provider by issuing a 1-token completion.

        We don't probe `/models` like the legacy clients did because:
          (a) Kimi /coding/v1/models is rate-limited and gates the same UA
          (b) Ollama /api/version doesn't validate the model is actually
              loaded — a 1-token completion is the strictest test
        """
        try:
            await litellm.acompletion(
                messages=[{"role": "user", "content": "."}],
                temperature=0.0,
                max_tokens=1,
                **self._kwargs(),
            )
        except Exception as exc:  # noqa: BLE001 — availability probe by design
            logger.warning(
                "LiteLLMClient(%s) is_available probe failed: %s: %s",
                self._model, type(exc).__name__, exc,
            )
            return False
        return True

    async def close(self) -> None:
        # LiteLLM owns its own httpx clients (pooled module-globally); no
        # per-instance cleanup needed. Keep the method for ABC compat with
        # legacy callers that still call client.close() in fixtures.
        return None


def _extract_from_thinking(thinking: str) -> str:
    """Extract usable content from a thinking/reasoning field when content is empty.

    Mirrors the legacy `OllamaClient._extract_from_thinking` heuristics so
    pipeline behavior is byte-identical when LiteLLM happens to surface a
    thinking model's output via the reasoning_content channel.

    1. Last fenced ```json block wins
    2. Falls back to first raw {...} match
    3. Falls back to the entire stripped thinking text
    """
    blocks = re.findall(r"```(?:json)?\s*\n(.*?)```", thinking, re.DOTALL)
    if blocks:
        return blocks[-1].strip()

    json_match = re.search(r"\{[\s\S]*\}", thinking)
    if json_match:
        return json_match.group(0).strip()

    return thinking.strip()
