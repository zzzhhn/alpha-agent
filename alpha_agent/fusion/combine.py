# alpha_agent/fusion/combine.py
"""Weighted composite + breakdown attribution. Pure function."""
from __future__ import annotations

import math
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

    Drop logic (the signal is excluded from composite with effective weight 0):
      1. confidence == 0  (signal said "I have no data")
      2. weight == 0       (e.g. calendar — display only)
      3. z is NaN/Inf      (signal lied about confidence; treat as no-info)

    Effective weights are re-normalized across the surviving signals.
    Composite is the sum of (z × weight_effective) over survivors only.
    """
    drop = {n for n, sc in signals.items() if sc["confidence"] == 0.0}
    drop |= {n for n, w in weights.items() if w == 0}
    drop |= {
        n for n, sc in signals.items()
        if not isinstance(sc["z"], (int, float)) or not math.isfinite(sc["z"])
    }
    eff = normalize_weights(weights, drop=drop)
    composite = 0.0
    breakdown: list[dict[str, Any]] = []
    for name, sc in signals.items():
        w_orig = weights.get(name, 0.0)
        w_eff = eff.get(name, 0.0)
        # Force contribution to 0 when signal is dropped, regardless of z
        # (NaN × 0 = NaN in Python, which would poison composite).
        if w_eff == 0:
            contribution = 0.0
        else:
            contribution = float(sc["z"]) * w_eff
        composite += contribution
        breakdown.append({
            "signal": name, "z": sc["z"],
            # confidence is included so a tiered cron can round-trip the
            # breakdown back into a sigs dict for combine() without losing
            # the drop signal (confidence == 0 means "no data").
            "confidence": sc["confidence"],
            "weight": w_orig,
            "weight_effective": w_eff, "contribution": contribution,
            "raw": sc["raw"], "source": sc["source"],
            "timestamp": sc["as_of"].isoformat(),
            "error": sc["error"],
        })
    return CombineResult(composite=composite, breakdown=breakdown)
