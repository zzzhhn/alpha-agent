"""AnomalyDetectorAgent — monitors service health and detects anomalies.

Blueprint Agent 3: Analyzes service health time-series to detect anomalous
patterns (latency spikes, throughput drops) and suggests remediation.

SLA: 3s (async — user can ignore). Fallback: return empty anomalies.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from alpha_agent.agents.base import BaseAgent
from alpha_agent.llm.base import Message
from alpha_agent.pipeline.state import PipelineState

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (Path(__file__).parent / "prompts" / "anomaly_detector.txt").read_text()


@dataclass(frozen=True)
class Anomaly:
    """A detected system anomaly."""

    service: str
    anomaly_type: str
    severity: str  # "critical" | "warning" | "info"
    description: str
    suggested_action: str


@dataclass(frozen=True)
class AnomalyReport:
    """Full anomaly detection report."""

    anomalies: tuple[Anomaly, ...]
    overall_health: str  # "healthy" | "degraded" | "critical"
    summary: str


class AnomalyDetectorAgent(BaseAgent):
    """Monitors system health metrics and detects anomalies.

    This agent is designed to run asynchronously — the UI should not
    block on its results. If it times out, the system shows no anomalies.

    Blueprint SLA: 3s (async, user can ignore).
    Input: last 1 hour of per-service metrics.
    """

    _sla_seconds = 3.0

    async def run(self, state: PipelineState) -> PipelineState:
        metrics = _build_metrics_context(state)
        if not metrics:
            return state

        messages = [
            Message(role="system", content=_SYSTEM_PROMPT),
            Message(role="user", content=metrics),
        ]

        response = await self._llm.chat(messages, temperature=0.2, max_tokens=1024)
        report = _parse_report(response.content)

        if report is not None:
            logger.info(
                "Anomaly detection: %s (%d anomalies)",
                report.overall_health,
                len(report.anomalies),
            )
            return state.with_updates(anomaly_report=report)

        logger.warning("Failed to parse anomaly report")
        return state

    def fallback(self, state: PipelineState) -> PipelineState:
        """Fallback: report healthy with no anomalies."""
        return state.with_updates(
            anomaly_report=AnomalyReport(
                anomalies=(),
                overall_health="unknown",
                summary="Anomaly detection timed out — status unknown.",
            )
        )


def _build_metrics_context(state: PipelineState) -> str:
    """Build metrics context from pipeline state.

    In production, this would read from a metrics store.
    For now, we pull whatever system info is in state.
    """
    # The orchestrator should inject system_metrics into state
    metrics = getattr(state, "system_metrics", None)
    if metrics is None:
        return ""

    if isinstance(metrics, dict):
        return json.dumps(metrics, indent=2, default=str)
    return str(metrics)


def _parse_report(text: str) -> AnomalyReport | None:
    """Parse LLM JSON response into an AnomalyReport."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.endswith("```"):
            cleaned = cleaned[: cleaned.rfind("```")]

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return None

    anomalies_raw = data.get("anomalies", [])
    anomalies = tuple(
        Anomaly(
            service=a.get("service", "unknown"),
            anomaly_type=a.get("type", "unknown"),
            severity=a.get("severity", "info"),
            description=a.get("description", ""),
            suggested_action=a.get("suggested_action", ""),
        )
        for a in anomalies_raw
    )

    return AnomalyReport(
        anomalies=anomalies,
        overall_health=data.get("overall_health", "unknown"),
        summary=data.get("summary", ""),
    )
