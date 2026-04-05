"""EvalAgent — evaluates backtested factors: accept, reject, or refine."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from alpha_agent.agents.base import BaseAgent
from alpha_agent.llm.base import Message
from alpha_agent.pipeline.state import EvaluationDecision, FactorResult, PipelineState

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (Path(__file__).parent / "prompts" / "evaluation.txt").read_text()

_MAX_RETRIES = 3


def _format_results(results: tuple[FactorResult, ...]) -> str:
    """Format backtest results into a readable string for the LLM."""
    lines: list[str] = []
    for r in results:
        decay_str = ", ".join(f"{v:.4f}" for v in r.alpha_decay[:5])
        lines.append(
            f"Expression: {r.candidate.expression}\n"
            f"  Hypothesis: {r.candidate.hypothesis_name}\n"
            f"  IC Mean: {r.ic_mean:+.4f}, ICIR: {r.icir:+.4f}\n"
            f"  Rank IC: {r.rank_ic_mean:+.4f}\n"
            f"  Sharpe: {r.sharpe_ratio:+.4f}, Max DD: {r.max_drawdown:+.2%}\n"
            f"  Turnover: {r.turnover:.4f}\n"
            f"  Alpha Decay (lags 1-5): [{decay_str}]"
        )
    return "\n\n".join(lines)


class EvalAgent(BaseAgent):
    """Evaluates backtested factors and decides: accept, reject, or refine."""

    async def run(self, state: PipelineState) -> PipelineState:
        if not state.results:
            logger.warning("No results to evaluate")
            return state.with_updates(
                evaluation=EvaluationDecision(
                    decision="reject",
                    feedback="No factors to evaluate",
                    suggestions=(),
                    best_factor=None,
                )
            )

        results_text = _format_results(state.results)
        user_content = (
            f"Evaluate these backtested factors (iteration {state.iteration + 1}"
            f"/{state.max_iterations}):\n\n{results_text}"
        )

        messages = [
            Message(role="system", content=_SYSTEM_PROMPT),
            Message(role="user", content=user_content),
        ]

        for attempt in range(1, _MAX_RETRIES + 1):
            response = await self._llm.chat(messages, temperature=0.3)
            decision = self._parse_decision(response.content, state.results)
            if decision is not None:
                logger.info(
                    "Evaluation (attempt %d): %s", attempt, decision.decision
                )
                return state.with_updates(
                    evaluation=decision,
                    prior_feedback=decision.feedback,
                )
            logger.warning(
                "Failed to parse evaluation (attempt %d): %s",
                attempt,
                response.content[:200],
            )

        # Fallback: reject if all retries failed
        logger.error("All evaluation attempts failed, defaulting to reject")
        return state.with_updates(
            evaluation=EvaluationDecision(
                decision="reject",
                feedback="Failed to parse LLM evaluation response",
                suggestions=(),
                best_factor=None,
            )
        )

    def _parse_decision(
        self, text: str, results: tuple[FactorResult, ...]
    ) -> EvaluationDecision | None:
        """Parse LLM JSON response into an EvaluationDecision."""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
            if cleaned.endswith("```"):
                cleaned = cleaned[: cleaned.rfind("```")]

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            return None

        decision_str = data.get("decision", "").lower()
        if decision_str not in ("accept", "reject", "refine"):
            return None

        feedback = data.get("feedback", "")
        suggestions = tuple(data.get("suggestions", []))
        best_expr = data.get("best_factor_expression", "")

        best_factor = None
        if decision_str == "accept" and best_expr:
            for r in results:
                if r.candidate.expression == best_expr:
                    best_factor = r
                    break
            if best_factor is None and results:
                best_factor = max(results, key=lambda r: abs(r.icir))

        return EvaluationDecision(
            decision=decision_str,
            feedback=feedback,
            suggestions=suggestions,
            best_factor=best_factor,
        )
