"""Abstract LLM client interface and shared types."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Message:
    """A single message in a chat conversation."""

    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(frozen=True)
class LLMResponse:
    """Response from an LLM API call."""

    content: str
    model: str
    prompt_tokens: int
    completion_tokens: int


class LLMClient(ABC):
    """Abstract interface for LLM providers.

    Implementations: OllamaClient, OpenAIClient, KimiClient, LiteLLMClient.
    All clients expose the same async chat() method, plus an optional
    stream_chat() that yields incremental text chunks. Implementations
    that haven't wired a native streaming path inherit the default
    fallback below which awaits the one-shot chat() and yields the full
    response as a single chunk — callers using
    `async for chunk in client.stream_chat(...)` always work, just
    without real token-by-token delivery.
    """

    @abstractmethod
    async def chat(
        self,
        messages: list[Message],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Send messages and get a completion."""
        ...

    async def stream_chat(
        self,
        messages: list[Message],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        """Yield incremental text deltas as the LLM generates the response.

        Default = non-streaming: await chat() and yield the entire content
        as one chunk. Subclasses with a real SSE / chunk stream override
        this; callers don't need to branch on provider.
        """
        resp = await self.chat(
            messages, temperature=temperature, max_tokens=max_tokens,
        )
        if resp.content:
            yield resp.content

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if the LLM service is reachable."""
        ...
