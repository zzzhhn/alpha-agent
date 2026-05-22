# alpha_agent/fusion/rating.py
"""5-tier mapping + confidence (signal-agreement gauge)."""
from __future__ import annotations

import math
import os
from typing import Iterable, Literal

import numpy as np

from alpha_agent.config_store import get_config

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
    t = get_config(
        "rating.tier_thresholds",
        {"buy": 1.5, "ow": 0.5, "hold": -0.5, "uw": -1.5},
    )
    if composite > t["buy"]:
        return "BUY"
    if composite > t["ow"]:
        return "OW"
    if composite >= t["hold"]:
        return "HOLD"
    if composite >= t["uw"]:
        return "UW"
    return "SELL"


def _resolve_band_width() -> float:
    """Read rating.no_trade_band from config store, falling back to
    ALPHA_TIER_BAND_Z env var (default 0.15).

    Config store takes precedence when a DB row is set; env var is the
    historic default so behavior is byte-identical with a cold cache.
    """
    raw = os.environ.get("ALPHA_TIER_BAND_Z", "0.15").strip()
    try:
        env_default = float(raw)
    except ValueError:
        env_default = 0.15
    # Reject negative or absurdly wide env defaults before passing them as
    # the fallback; the config value gets the same clamp below.
    if not 0 <= env_default <= 0.5:
        env_default = 0.15
    band = get_config("rating.no_trade_band", env_default)
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
    # Source cutoffs from config so band ranges stay consistent with map_to_tier.
    t = get_config(
        "rating.tier_thresholds",
        {"buy": 1.5, "ow": 0.5, "hold": -0.5, "uw": -1.5},
    )
    # Build the hysteresis-extended bounds of prev_tier: each tier widens
    # by `band` on the side where it would otherwise lose to a neighbour.
    bounds = {
        "BUY":  (t["buy"]  - band, math.inf),
        "OW":   (t["ow"]   - band, t["buy"]  + band),
        "HOLD": (t["hold"] - band, t["ow"]   + band),
        "UW":   (t["uw"]   - band, t["hold"] + band),
        "SELL": (-math.inf,        t["uw"]   + band),
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
