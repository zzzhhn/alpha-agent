# alpha_agent/fusion/normalize.py
"""Cross-section z-score + winsorize. Pure function, no IO."""
from __future__ import annotations

import math
from typing import Any, Mapping

import numpy as np

from alpha_agent.signals.base import SignalScore


def normalize_cross_section(
    inputs: Mapping[str, Any],
    *,
    raw_field: str | None = None,
    clip_sigma: float = 3.0,
) -> dict[str, float]:
    """Compute z-scores across the universe.

    inputs may be either:
      - {ticker: float} of raw values, or
      - {ticker: SignalScore} where we use SignalScore[raw_field] (default 'raw')
    confidence==0 entries are excluded from mean/sigma but get z=0 in output.
    """
    if raw_field is None:
        # plain {ticker: float}
        vals = {t: float(v) for t, v in inputs.items()}
        excluded: set[str] = set()
    else:
        vals = {}
        excluded = set()
        for t, sc in inputs.items():
            if sc["confidence"] == 0.0:
                excluded.add(t)
            else:
                v = sc[raw_field]
                vals[t] = float(v) if isinstance(v, (int, float)) else float(sc["z"])
    if not vals:
        return {t: 0.0 for t in inputs}
    arr = np.array(list(vals.values()), dtype=float)
    mu = float(np.nanmean(arr))
    sigma = float(np.nanstd(arr))
    if sigma == 0 or math.isnan(sigma):
        return {t: 0.0 for t in inputs}
    out = {t: float(np.clip((v - mu) / sigma, -clip_sigma, clip_sigma))
           for t, v in vals.items()}
    for t in excluded:
        out[t] = 0.0
    return out
