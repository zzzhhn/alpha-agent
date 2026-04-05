"""HypothesisAgent — generates market hypotheses from natural language queries."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from alpha_agent.agents.base import BaseAgent
from alpha_agent.llm.base import Message
from alpha_agent.pipeline.state import Hypothesis, PipelineState

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (Path(__file__).parent / "prompts" / "hypothesis.txt").read_text()

_MAX_RETRIES = 3


class HypothesisAgent(BaseAgent):
    """Takes a natural language research query and generates market hypotheses.

    Input: state.query (e.g., "find short-term reversal factors")
    Output: state with hypotheses populated
    """

    async def run(self, state: PipelineState) -> PipelineState:
        user_content = f"Research direction: {state.query}"
        if state.prior_feedback:
            user_content += (
                f"\n\nPrevious iteration feedback (improve on this):\n{state.prior_feedback}"
            )

        messages = [
            Message(role="system", content=_SYSTEM_PROMPT),
            Message(role="user", content=user_content),
        ]

        for attempt in range(1, _MAX_RETRIES + 1):
            response = await self._llm.chat(messages, temperature=0.7)
            hypotheses = _parse_hypotheses(response.content)
            if hypotheses:
                logger.info("Generated %d hypotheses (attempt %d)", len(hypotheses), attempt)
                return state.with_updates(hypotheses=tuple(hypotheses))
            logger.warning("Failed to parse hypotheses (attempt %d): %s", attempt, response.content[:200])

        logger.error("All %d attempts to generate hypotheses failed", _MAX_RETRIES)
        return state


def _parse_hypotheses(text: str) -> list[Hypothesis]:
    """Extract hypotheses from LLM JSON output, tolerating markdown fences."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.endswith("```"):
            cleaned = cleaned[: cleaned.rfind("```")]

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return []

    items = data.get("hypotheses", [])
    result = []
    for item in items:
        name = item.get("name", "")
        rationale = item.get("rationale", "")
        expected_type = item.get("expected_type", "unknown")
        if name and rationale:
            result.append(Hypothesis(name=name, rationale=rationale, expected_type=expected_type))
    return result
