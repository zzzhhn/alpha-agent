"""Abstract LLM client interface and shared types."""

from __future__ import annotations

from abc import ABC, abstractmethod
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

    Implementations: OllamaClient, OpenAIClient.
    All clients expose the same async chat() method.
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

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if the LLM service is reachable."""
        ...
