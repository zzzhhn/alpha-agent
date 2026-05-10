# alpha_agent/fusion/rating.py
"""5-tier mapping + confidence (signal-agreement gauge)."""
from __future__ import annotations

import math
from typing import Iterable, Literal

import numpy as np

Tier = Literal["BUY", "OW", "HOLD", "UW", "SELL"]


def map_to_tier(composite: float) -> Tier:
    # NaN composites (any signal returning NaN propagates through combine).
    # All comparisons with NaN are False — without this guard the function
    # falls through to SELL, which is a wrong-direction bias.  HOLD = "not
    # enough info to take a side" matches the spec contract.
    if composite is None or (isinstance(composite, float) and math.isnan(composite)):
        return "HOLD"
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
    # NaN-safe variance: skip NaN z values rather than poisoning the result.
    arr = arr[~np.isnan(arr)]
    if arr.size == 0:
        return 0.0
    var = float(np.var(arr))
    return float(1.0 / (1.0 + var))
