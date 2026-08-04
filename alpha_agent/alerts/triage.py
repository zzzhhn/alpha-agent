"""Deterministic alert severity and decision-relevance assessment.

The scoring deliberately contains no LLM-generated causal explanation. It
combines facts already known to the product: event type, age, current paper
position, latest recommendation, watchlist membership, and evidence count.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal, TypedDict

Severity = Literal["critical", "warning", "info"]
Relevance = Literal["position", "recommendation", "market", "watchlist", "record"]


class TriageAssessment(TypedDict):
    severity: Severity
    relevance: Relevance
    triage_score: int
    freshness_score: int
    confidence_score: int
    confidence: Literal["high", "medium", "low"]
    source_count: int
    stale: bool


def _number(payload: dict[str, Any], key: str) -> float | None:
    value = payload.get(key)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _severity(alert_type: str, payload: dict[str, Any]) -> Severity:
    if alert_type == "rating_change":
        target = str(payload.get("to", "")).upper()
        return "critical" if target in {"UW", "SELL"} else "warning"
    if alert_type == "gap_3sigma":
        sigma = abs(_number(payload, "gap_sigma") or 0.0)
        return "critical" if sigma >= 4.0 else "warning"
    if alert_type == "iv_spike":
        percentile = _number(payload, "iv_percentile") or 0.0
        return "critical" if percentile >= 95.0 else "warning"
    if alert_type == "news_velocity":
        count = _number(payload, "n_24h") or 0.0
        if count >= 30:
            return "critical"
        return "warning" if count >= 20 else "info"
    if alert_type == "score_spike":
        delta = abs(_number(payload, "delta") or 0.0)
        return "warning" if delta >= 0.35 else "info"
    return "info"


def assess_alert(
    *,
    alert_type: str,
    payload: dict[str, Any] | None,
    ticker: str,
    created_at: datetime,
    in_position: bool,
    in_recommendation: bool,
    in_watchlist: bool,
    now: datetime | None = None,
) -> TriageAssessment:
    facts = payload or {}
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    created = created_at if created_at.tzinfo else created_at.replace(tzinfo=UTC)
    age_hours = max(0.0, (current - created).total_seconds() / 3600.0)

    severity = _severity(alert_type, facts)
    severity_score = {"critical": 25, "warning": 15, "info": 5}[severity]
    if in_position:
        relevance: Relevance = "position"
        relevance_score = 40
    elif in_recommendation:
        relevance = "recommendation"
        relevance_score = 30
    elif ticker.upper() in {"SPY", "QQQ", "IWM", "VIX", "RSP"}:
        relevance = "market"
        relevance_score = 20
    elif in_watchlist:
        relevance = "watchlist"
        relevance_score = 15
    else:
        relevance = "record"
        relevance_score = 0

    if age_hours <= 1:
        freshness_score = 20
    elif age_hours <= 6:
        freshness_score = 15
    elif age_hours <= 24:
        freshness_score = 10
    elif age_hours <= 72:
        freshness_score = 5
    else:
        freshness_score = 0

    raw_sources = facts.get("source_count", 1)
    source_count = raw_sources if isinstance(raw_sources, int) and raw_sources > 0 else 1
    if source_count >= 3:
        confidence, confidence_score = "high", 15
    elif source_count == 2:
        confidence, confidence_score = "medium", 10
    else:
        confidence, confidence_score = "low", 5

    return {
        "severity": severity,
        "relevance": relevance,
        "triage_score": min(
            100,
            relevance_score + severity_score + freshness_score + confidence_score,
        ),
        "freshness_score": freshness_score,
        "confidence_score": confidence_score,
        "confidence": confidence,
        "source_count": source_count,
        "stale": age_hours > 168,
    }
