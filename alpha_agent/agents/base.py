"""Base class for all pipeline agents with SLA enforcement."""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod

from alpha_agent.llm.base import LLMClient
from alpha_agent.pipeline.state import PipelineState

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Abstract agent that processes pipeline state.

    Each agent receives the current state and returns a new
    (immutable) state with its contribution added.

    Subclasses set ``_sla_seconds`` to enforce a timeout.
    When ``run()`` exceeds the SLA, ``fallback()`` is called instead.
    """

    _sla_seconds: float = 0  # 0 = no SLA enforcement

    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    async def execute(self, state: PipelineState) -> PipelineState:
        """Run the agent with SLA enforcement and telemetry.

        Prefer calling ``execute()`` over ``run()`` directly — it
        wraps ``run()`` with timeout, fallback, and latency logging.
        """
        start = time.monotonic()

        try:
            if self._sla_seconds > 0:
                result = await asyncio.wait_for(
                    self.run(state),
                    timeout=self._sla_seconds,
                )
            else:
                result = await self.run(state)

            elapsed = time.monotonic() - start
            logger.info(
                "%s completed in %.2fs (SLA: %s)",
                self.__class__.__name__,
                elapsed,
                f"{self._sla_seconds}s" if self._sla_seconds else "none",
            )
            return result

        except asyncio.TimeoutError:
            elapsed = time.monotonic() - start
            logger.warning(
                "%s exceeded SLA (%.2fs > %.1fs), using fallback",
                self.__class__.__name__,
                elapsed,
                self._sla_seconds,
            )
            return self.fallback(state)

        except Exception:
            elapsed = time.monotonic() - start
            logger.error(
                "%s failed after %.2fs, using fallback",
                self.__class__.__name__,
                elapsed,
                exc_info=True,
            )
            return self.fallback(state)

    @abstractmethod
    async def run(self, state: PipelineState) -> PipelineState:
        """Process the state and return an updated copy."""
        ...

    def fallback(self, state: PipelineState) -> PipelineState:
        """Default fallback: return state unchanged.

        Subclasses override this to provide degraded results
        (e.g., raw JSON, static suggestions).
        """
        return state
