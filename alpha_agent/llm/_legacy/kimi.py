"""Kimi For Coding client (Anthropic-compat protocol).

Endpoint: https://api.kimi.com/coding/v1
Docs: https://moonshotai.github.io/kimi-cli/en/configuration/providers.html

The "/v1/chat/completions" (OpenAI-compat) path exists but enforces a
server-side temperature constraint that rejects every explicit value.
The "/v1/messages" (Anthropic-compat) path has no such quirk, so we use it.

Access is gated by User-Agent: the server allow-lists known coding agents
(Kimi CLI, Claude Code, Roo Code, Kilo Code). We send a claude-cli UA.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator

import httpx

from alpha_agent.llm.base import LLMClient, LLMResponse, Message

logger = logging.getLogger(__name__)


_UA = "claude-cli/1.0.0 (external, cli)"
_ANTHROPIC_VERSION = "2023-06-01"


class KimiClient(LLMClient):
    """Kimi For Coding via the Anthropic-compatible /messages endpoint."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.kimi.com/coding/v1",
        model: str = "kimi-for-coding",
    ) -> None:
        self._model = model
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={
                "x-api-key": api_key,
                "anthropic-version": _ANTHROPIC_VERSION,
                "User-Agent": _UA,
                "Content-Type": "application/json",
            },
            # Read timeout must exceed the caller's wall clock (propose_factors
            # wraps chat() in asyncio.wait_for): Kimi-for-Coding generating a full
            # multi-factor proposal now takes >120s, and the old flat 120s httpx
            # cap ReadTimeout'd the non-streaming request before the caller's
            # wait_for could govern — surfacing as "提议失败: ReadTimeout". A high
            # read timeout lets the caller's wall clock be the single, clean cap;
            # a short connect keeps a dead endpoint failing fast.
            timeout=httpx.Timeout(260.0, connect=15.0),
        )

    async def chat(
        self,
        messages: list[Message],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        system_prompts = [m.content for m in messages if m.role == "system"]
        convo = [
            {"role": m.role, "content": m.content}
            for m in messages
            if m.role in ("user", "assistant")
        ]

        payload: dict[str, object] = {
            "model": self._model,
            "messages": convo,
            "max_tokens": max_tokens,
        }
        if system_prompts:
            payload["system"] = "\n\n".join(system_prompts)

        response = await self._client.post("/messages", json=payload)
        response.raise_for_status()
        data = response.json()

        text_parts = [
            block.get("text", "")
            for block in data.get("content", [])
            if block.get("type") == "text"
        ]
        usage = data.get("usage", {})

        return LLMResponse(
            content="".join(text_parts),
            model=data.get("model", self._model),
            prompt_tokens=usage.get("input_tokens", 0),
            completion_tokens=usage.get("output_tokens", 0),
        )

    async def stream_chat(
        self,
        messages: list[Message],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        """Yield text deltas as Kimi generates them via Anthropic-compat SSE.

        Anthropic event types we care about:
          - content_block_delta { delta: { type: "text_delta", text: "..." } }
            → emit text
          - message_stop → terminate
          - ping / message_start / content_block_start / content_block_stop /
            message_delta → ignored (no user-visible content)

        Lines that don't parse as JSON, lack a known event type, or are
        empty are silently skipped; the loop continues until the server
        closes the stream or message_stop fires. Caller wraps any upstream
        HTTP error.
        """
        system_prompts = [m.content for m in messages if m.role == "system"]
        convo = [
            {"role": m.role, "content": m.content}
            for m in messages
            if m.role in ("user", "assistant")
        ]
        payload: dict[str, object] = {
            "model": self._model,
            "messages": convo,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if system_prompts:
            payload["system"] = "\n\n".join(system_prompts)

        async with self._client.stream(
            "POST", "/messages", json=payload,
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                # Anthropic SSE format is: `event: <type>\ndata: <json>\n\n`
                # We only need the `data:` lines; `event:` lines are
                # informational metadata that duplicates `type` inside data.
                if not line.startswith("data:"):
                    continue
                payload_str = line[5:].lstrip()
                if not payload_str or payload_str == "[DONE]":
                    continue
                try:
                    evt = json.loads(payload_str)
                except json.JSONDecodeError:
                    continue
                if evt.get("type") == "content_block_delta":
                    delta = evt.get("delta") or {}
                    text = delta.get("text", "") if delta.get("type") == "text_delta" else ""
                    if text:
                        yield text
                elif evt.get("type") == "message_stop":
                    break

    async def is_available(self) -> bool:
        try:
            response = await self._client.get("/models")
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            logger.warning("KimiClient /models unreachable: %s: %s", type(exc).__name__, exc)
            return False
        except Exception as exc:
            logger.warning("KimiClient /models raised %s: %s", type(exc).__name__, exc)
            return False
        if response.status_code != 200:
            logger.warning(
                "KimiClient /models returned %s: %s",
                response.status_code,
                response.text[:200],
            )
            return False
        return True

    async def close(self) -> None:
        await self._client.aclose()
