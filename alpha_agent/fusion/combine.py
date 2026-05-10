# alpha_agent/fusion/combine.py
"""Weighted composite + breakdown attribution. Pure function."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from alpha_agent.signals.base import SignalScore
from alpha_agent.fusion.weights import normalize_weights


@dataclass
class CombineResult:
    composite: float
    breakdown: list[dict[str, Any]] = field(default_factory=list)


def combine(
    signals: Mapping[str, SignalScore],
    weights: Mapping[str, float],
) -> CombineResult:
    """signals: {signal_name: SignalScore}.
    weights: {signal_name: weight}; calendar=0 always excluded.
    Confidence==0 signals: weight retained in breakdown for display, but
    contribution=0; effective weights re-normalize across the rest.
    """
    drop = {n for n, sc in signals.items() if sc["confidence"] == 0.0}
    drop |= {n for n, w in weights.items() if w == 0}
    eff = normalize_weights(weights, drop=drop)
    composite = 0.0
    breakdown: list[dict[str, Any]] = []
    for name, sc in signals.items():
        w_orig = weights.get(name, 0.0)
        w_eff = eff.get(name, 0.0)
        contribution = sc["z"] * w_eff
        composite += contribution
        breakdown.append({
            "signal": name, "z": sc["z"], "weight": w_orig,
            "weight_effective": w_eff, "contribution": contribution,
            "raw": sc["raw"], "source": sc["source"],
            "timestamp": sc["as_of"].isoformat(),
            "error": sc["error"],
        })
    return CombineResult(composite=composite, breakdown=breakdown)
