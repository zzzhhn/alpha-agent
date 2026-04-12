"""RiskAdvisorAgent — provides portfolio risk management advice.

Blueprint Agent 4: Analyzes current positions, volatility, and market regime
to recommend position adjustments using Kelly criterion.

SLA: 2.5s — fallback shows Kelly-based static advice.
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

_SYSTEM_PROMPT = (Path(__file__).parent / "prompts" / "risk_advisor.txt").read_text()

# Half-Kelly default for conservative sizing
_HALF_KELLY_DEFAULT = 0.125


@dataclass(frozen=True)
class PositionAdjustment:
    """Suggested position weight change."""

    ticker: str
    current_weight: float
    suggested_weight: float
    reason: str


@dataclass(frozen=True)
class RiskAdvice:
    """Full risk advisory output."""

    advice: str
    position_adjustments: tuple[PositionAdjustment, ...]
    kelly_fraction: float
    max_drawdown_warning: bool
    concentration_risk: str  # "low" | "medium" | "high"
    overall_risk_score: float  # 0-1


class RiskAdvisorAgent(BaseAgent):
    """Provides portfolio risk management advice.

    Blueprint SLA: 2.5s (timeout → Kelly-based static advice).
    Input: current positions, realized volatility, VaR estimate.
    """

    _sla_seconds = 2.5

    async def run(self, state: PipelineState) -> PipelineState:
        context = _build_risk_context(state)
        if not context:
            return state

        messages = [
            Message(role="system", content=_SYSTEM_PROMPT),
            Message(role="user", content=context),
        ]

        response = await self._llm.chat(messages, temperature=0.2, max_tokens=1024)
        advice = _parse_advice(response.content)

        if advice is not None:
            logger.info(
                "Risk advice: score=%.2f, concentration=%s",
                advice.overall_risk_score,
                advice.concentration_risk,
            )
            return state.with_updates(risk_advice=advice)

        logger.warning("Failed to parse risk advice")
        return state

    def fallback(self, state: PipelineState) -> PipelineState:
        """Fallback: provide conservative Kelly-based static advice."""
        advice = RiskAdvice(
            advice=(
                "LLM risk analysis timed out. "
                "Defaulting to half-Kelly conservative sizing. "
                "Consider reducing exposure until full analysis is available."
            ),
            position_adjustments=(),
            kelly_fraction=_HALF_KELLY_DEFAULT,
            max_drawdown_warning=False,
            concentration_risk="unknown",
            overall_risk_score=0.5,
        )
        return state.with_updates(risk_advice=advice)


def _build_risk_context(state: PipelineState) -> str:
    """Build risk context from pipeline state.

    In production, the orchestrator injects positions and risk metrics.
    """
    parts: list[str] = []

    # Pull from extended state attributes
    positions = getattr(state, "positions", None)
    if positions:
        parts.append("Current positions:")
        if isinstance(positions, (list, tuple)):
            for p in positions:
                parts.append(f"  - {p}")
        else:
            parts.append(f"  {positions}")

    risk_metrics = getattr(state, "risk_metrics", None)
    if risk_metrics:
        parts.append(f"\nRisk metrics: {json.dumps(risk_metrics, default=str)}")

    # Include evaluation context if available
    if state.evaluation:
        parts.append(f"\nLatest evaluation: {state.evaluation.decision}")
        parts.append(f"Feedback: {state.evaluation.feedback}")

    if state.results:
        best_sharpe = max(r.sharpe_ratio for r in state.results)
        worst_dd = min(r.max_drawdown for r in state.results)
        parts.append(f"\nBest Sharpe in pool: {best_sharpe:+.4f}")
        parts.append(f"Worst drawdown in pool: {worst_dd:+.2%}")

    return "\n".join(parts) if parts else ""


def _parse_advice(text: str) -> RiskAdvice | None:
    """Parse LLM JSON response into RiskAdvice."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.endswith("```"):
            cleaned = cleaned[: cleaned.rfind("```")]

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return None

    advice_text = data.get("advice", "")
    if not advice_text:
        return None

    adjustments_raw = data.get("position_adjustments", [])
    adjustments = tuple(
        PositionAdjustment(
            ticker=a.get("ticker", ""),
            current_weight=float(a.get("current_weight", 0)),
            suggested_weight=float(a.get("suggested_weight", 0)),
            reason=a.get("reason", ""),
        )
        for a in adjustments_raw
        if a.get("ticker")
    )

    return RiskAdvice(
        advice=advice_text,
        position_adjustments=adjustments,
        kelly_fraction=float(data.get("kelly_fraction", _HALF_KELLY_DEFAULT)),
        max_drawdown_warning=bool(data.get("max_drawdown_warning", False)),
        concentration_risk=data.get("concentration_risk", "unknown"),
        overall_risk_score=float(data.get("overall_risk_score", 0.5)),
    )
