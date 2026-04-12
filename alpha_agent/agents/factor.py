"""FactorAgent — generates factor expressions from hypotheses."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from alpha_agent.agents.base import BaseAgent
from alpha_agent.factor_engine.parser import ExprParser, ParseError
from alpha_agent.llm.base import Message
from alpha_agent.pipeline.state import FactorCandidate, PipelineState

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (Path(__file__).parent / "prompts" / "factor.txt").read_text()

_MAX_RETRIES = 3


class FactorAgent(BaseAgent):
    """Takes hypotheses and generates factor expressions.

    Input: state.hypotheses
    Output: state with factors populated (only syntactically valid ones)

    Blueprint Agent 1 SLA: 2s (timeout → fallback to parse error).
    """

    _sla_seconds = 2.0

    def __init__(self, llm: object) -> None:
        super().__init__(llm)
        self._parser = ExprParser()

    async def run(self, state: PipelineState) -> PipelineState:
        if not state.hypotheses:
            logger.warning("No hypotheses to generate factors from")
            return state

        hypotheses_text = "\n".join(
            f"- {h.name}: {h.rationale} (type: {h.expected_type})"
            for h in state.hypotheses
        )
        user_content = f"Generate factor expressions for these hypotheses:\n{hypotheses_text}"
        if state.prior_feedback:
            user_content += f"\n\nPrevious feedback:\n{state.prior_feedback}"

        messages = [
            Message(role="system", content=_SYSTEM_PROMPT),
            Message(role="user", content=user_content),
        ]

        all_candidates: list[FactorCandidate] = []

        for attempt in range(1, _MAX_RETRIES + 1):
            response = await self._llm.chat(messages, temperature=0.5)
            candidates = self._parse_and_validate(response.content)
            if candidates:
                all_candidates.extend(candidates)
                logger.info(
                    "Generated %d valid factors (attempt %d)", len(candidates), attempt
                )
                break
            logger.warning(
                "No valid factors parsed (attempt %d): %s", attempt, response.content[:200]
            )

        if not all_candidates:
            logger.error("All attempts to generate factors failed")

        return state.with_updates(factors=tuple(all_candidates))

    def _parse_and_validate(self, text: str) -> list[FactorCandidate]:
        """Extract factors from LLM output, keeping only parseable expressions."""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
            if cleaned.endswith("```"):
                cleaned = cleaned[: cleaned.rfind("```")]

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            return []

        items = data.get("factors", [])
        valid: list[FactorCandidate] = []

        for item in items:
            expr_str = item.get("expression", "")
            hypothesis_name = item.get("hypothesis_name", "")
            rationale = item.get("rationale", "")

            if not expr_str:
                continue

            try:
                self._parser.parse(expr_str)
            except ParseError as e:
                logger.warning("Skipping invalid expression %r: %s", expr_str, e)
                continue

            valid.append(
                FactorCandidate(
                    expression=expr_str,
                    hypothesis_name=hypothesis_name,
                    rationale=rationale,
                )
            )

        return valid
