"""ResearchSummaryAgent — generates human-readable decision explanations.

Blueprint Agent 2: Analyzes the complete decision chain (regime, predictions,
risk assessment, execution) and produces a human-readable explanation.

SLA: 1.5s — fallback shows raw JSON.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from alpha_agent.agents.base import BaseAgent
from alpha_agent.llm.base import LLMClient, Message
from alpha_agent.pipeline.state import PipelineState

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (Path(__file__).parent / "prompts" / "research_summary.txt").read_text()

_MAX_CONTEXT_EVENTS = 20


@dataclass(frozen=True)
class ResearchSummary:
    """Structured research summary output."""

    summary: str
    key_factors: tuple[str, ...]
    confidence_assessment: str
    risk_notes: str


class ResearchSummaryAgent(BaseAgent):
    """Generates human-readable research summaries for trading decisions.

    Input: decision context (regime, predictions, gate results, decision)
    Output: structured explanation suitable for audit log display

    Blueprint SLA: 1.5s (timeout → display raw JSON instead).
    """

    _sla_seconds = 1.5

    async def run(self, state: PipelineState) -> PipelineState:
        context = _build_decision_context(state)
        if not context:
            logger.warning("No decision context to summarize")
            return state

        messages = [
            Message(role="system", content=_SYSTEM_PROMPT),
            Message(role="user", content=context),
        ]

        response = await self._llm.chat(messages, temperature=0.3, max_tokens=1024)
        parsed = _parse_summary(response.content)

        if parsed is not None:
            logger.info("Research summary generated: %s", parsed.confidence_assessment)
            return state.with_updates(
                research_summary=parsed,
            )

        logger.warning("Failed to parse research summary")
        return state

    def fallback(self, state: PipelineState) -> PipelineState:
        """Fallback: produce a raw-data summary without LLM."""
        summary = ResearchSummary(
            summary=f"Decision based on {len(state.results)} factor results.",
            key_factors=tuple(
                r.candidate.expression for r in state.results[:3]
            ) if state.results else (),
            confidence_assessment="unknown",
            risk_notes="LLM summary unavailable — showing raw data.",
        )
        return state.with_updates(research_summary=summary)


def _build_decision_context(state: PipelineState) -> str:
    """Build a concise context string from pipeline state for the LLM."""
    parts: list[str] = []

    if state.evaluation:
        parts.append(f"Decision: {state.evaluation.decision}")
        parts.append(f"Feedback: {state.evaluation.feedback}")

    if state.results:
        parts.append(f"\nBacktested factors ({len(state.results)}):")
        for r in state.results[:_MAX_CONTEXT_EVENTS]:
            parts.append(
                f"  - {r.candidate.expression}: "
                f"IC={r.ic_mean:+.4f}, ICIR={r.icir:+.4f}, "
                f"Sharpe={r.sharpe_ratio:+.4f}"
            )

    if state.hypotheses:
        parts.append(f"\nHypotheses ({len(state.hypotheses)}):")
        for h in state.hypotheses:
            parts.append(f"  - {h.name}: {h.rationale}")

    return "\n".join(parts) if parts else ""


def _parse_summary(text: str) -> ResearchSummary | None:
    """Parse LLM JSON response into a ResearchSummary."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.endswith("```"):
            cleaned = cleaned[: cleaned.rfind("```")]

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return None

    summary = data.get("summary", "")
    if not summary:
        return None

    return ResearchSummary(
        summary=summary,
        key_factors=tuple(data.get("key_factors", [])),
        confidence_assessment=data.get("confidence_assessment", "unknown"),
        risk_notes=data.get("risk_notes", ""),
    )
