# alpha_agent/fusion/weights.py
"""Default fusion weights + redistribution helper.

Spec §3.1: 9 fusion signals sum to 1.0; calendar=0 (display only)."""
from __future__ import annotations

from typing import Mapping

DEFAULT_WEIGHTS: dict[str, float] = {
    "factor":     0.30,
    "technicals": 0.20,
    "analyst":    0.10,
    "earnings":   0.10,
    "news":       0.10,
    "insider":    0.05,
    "options":    0.05,
    "premarket":  0.05,
    "macro":      0.05,
    "calendar":   0.00,
}


def normalize_weights(
    weights: Mapping[str, float],
    *,
    drop: set[str] | None = None,
) -> dict[str, float]:
    """Drop excluded signals + re-normalize remaining to sum to 1.0."""
    drop = drop or set()
    kept = {k: v for k, v in weights.items() if k not in drop and v > 0}
    total = sum(kept.values())
    if total == 0:
        return {}
    return {k: v / total for k, v in kept.items()}
