# alpha_agent/fusion/rating.py
"""5-tier mapping + confidence (signal-agreement gauge)."""
from __future__ import annotations

import math
import os
from typing import Iterable, Literal

import numpy as np

Tier = Literal["BUY", "OW", "HOLD", "UW", "SELL"]

# Tier thresholds. Centralized constant so the band logic below stays in
# lockstep with map_to_tier; if either drifts the regression test in
# tests/fusion/test_rating.py catches it.
_TIER_THRESHOLDS: tuple[tuple[float, Tier], ...] = (
    (1.5, "BUY"),
    (0.5, "OW"),
    (-0.5, "HOLD"),
    (-1.5, "UW"),
)


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


def _resolve_band_width() -> float:
    """Read ALPHA_TIER_BAND_Z env var with safe default 0.15.

    Env-driven keeps the knob admin-only for v1 (single-user dev). When
    multi-user shipping arrives, swap for a user_settings lookup.
    """
    raw = os.environ.get("ALPHA_TIER_BAND_Z", "0.15").strip()
    try:
        band = float(raw)
    except ValueError:
        return 0.15
    # Reject negative or absurdly wide bands (1.0 would collapse the
    # entire HOLD-to-OW transition).
    if not 0 <= band <= 0.5:
        return 0.15
    return band


def map_to_tier_with_band(
    composite: float,
    prev_tier: Tier | str | None,
    band: float | None = None,
) -> Tier:
    """Hysteresis-banded tier mapping. Keeps `prev_tier` unless `composite`
    crosses ±`band` past the next threshold in the appropriate direction.

    The band cuts turnover from threshold-adjacent wobble (e.g. composite
    drifting between 0.49 and 0.51 would otherwise flip HOLD↔OW every cron
    tick). Once `composite` clearly clears the band edge, the tier follows.

    `prev_tier` None or "HOLD-from-cold-start" falls through to legacy
    map_to_tier — only an actual prior tier engages the band.

    `band` defaults to ALPHA_TIER_BAND_Z env var (default 0.15).
    """
    if band is None:
        band = _resolve_band_width()
    raw_tier = map_to_tier(composite)
    if prev_tier is None or prev_tier == raw_tier or band <= 0:
        return raw_tier
    # Build the hysteresis-extended bounds of prev_tier: each tier widens
    # by `band` on the side where it would otherwise lose to a neighbour.
    bounds = {
        "BUY":  (1.5 - band, math.inf),
        "OW":   (0.5 - band, 1.5 + band),
        "HOLD": (-0.5 - band, 0.5 + band),
        "UW":   (-1.5 - band, -0.5 + band),
        "SELL": (-math.inf, -1.5 + band),
    }
    if prev_tier not in bounds:
        return raw_tier
    lo, hi = bounds[prev_tier]
    # Composite that's still inside the extended prev_tier range = sticky.
    if lo <= composite <= hi:
        return prev_tier  # type: ignore[return-value]
    return raw_tier


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


def calibrated_confidence(zs: Iterable[float], cal_map=None) -> float:
    """compute_confidence passed through the Phase 1c calibration map
    (suppress overconfidence only). cal_map=None -> raw confidence unchanged."""
    from alpha_agent.backtest.confidence_calibration import apply_calibration
    return apply_calibration(compute_confidence(zs), cal_map)
