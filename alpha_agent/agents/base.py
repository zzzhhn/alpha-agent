"""Base class for all pipeline agents."""

from __future__ import annotations

from abc import ABC, abstractmethod

from alpha_agent.llm.base import LLMClient
from alpha_agent.pipeline.state import PipelineState


class BaseAgent(ABC):
    """Abstract agent that processes pipeline state.

    Each agent receives the current state and returns a new
    (immutable) state with its contribution added.
    """

    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    @abstractmethod
    async def run(self, state: PipelineState) -> PipelineState:
        """Process the state and return an updated copy."""
        ...
