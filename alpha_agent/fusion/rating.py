# alpha_agent/fusion/rating.py
"""5-tier mapping + confidence (signal-agreement gauge)."""
from __future__ import annotations

from typing import Iterable, Literal

import numpy as np

Tier = Literal["BUY", "OW", "HOLD", "UW", "SELL"]


def map_to_tier(composite: float) -> Tier:
    if composite > 1.5:
        return "BUY"
    if composite > 0.5:
        return "OW"
    if composite >= -0.5:
        return "HOLD"
    if composite >= -1.5:
        return "UW"
    return "SELL"


def compute_confidence(zs: Iterable[float]) -> float:
    """confidence = 1 / (1 + variance). Aligned signals -> ~1; disagreement -> ~0."""
    arr = np.asarray(list(zs), dtype=float)
    if arr.size == 0:
        return 0.0
    var = float(np.var(arr))
    return float(1.0 / (1.0 + var))
