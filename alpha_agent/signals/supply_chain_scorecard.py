"""Serenity-style supply-chain bottleneck scorecard (scoring core).

Faithful port of muxuuu/serenity-skill scripts/serenity_scorecard.py (MIT) into
the alpha-agent package, so the live signal path scores a thesis without
shelling out to the skill. Eight factors each rated 0-5 are weighted (weights
sum to 100); eight penalties each 0-5 subtract PENALTY_MULTIPLIER points; the
final score is clamped to [0, 100].

This module is pure scoring + the score -> z mapping. The persistence seam
(supply_chain_scorecard table) and the SignalScore wrapper live in
signals/supply_chain.py. Research-only: it ranks a thesis, it does not trade.
"""
from __future__ import annotations

from typing import Any

# Factor weights (sum = 100), verbatim from the serenity scorecard rubric.
WEIGHTS: dict[str, int] = {
    "demand_inflection": 15,
    "architecture_coupling": 10,
    "chokepoint_severity": 15,
    "supplier_concentration": 12,
    "expansion_difficulty": 12,
    "evidence_quality": 15,
    "valuation_disconnect": 11,
    "catalyst_timing": 10,
}

PENALTY_KEYS: tuple[str, ...] = (
    "dilution_financing",
    "governance",
    "geopolitics",
    "liquidity",
    "hype_risk",
    "accounting_quality",
    "cyclicality",
    "alternative_design_risk",
)

PENALTY_MULTIPLIER: float = 2.0

# Score -> z mapping. The bottleneck score is a [0, 100] conviction measure
# (how strongly the evidence says this name controls a scarce, hard-to-scale
# layer). Centre at 50 (a neutral thesis) and scale so the full range spans the
# clipped z band: score 100 -> +3, score 50 -> 0, score 0 -> -3. A strong
# chokepoint is a positive tilt; a weak/penalised thesis tilts negative.
_Z_CENTER: float = 50.0
_Z_SCALE: float = 50.0 / 3.0  # ~16.67 points per sigma
_Z_CLIP: float = 3.0


def _num_0_to_5(value: Any, label: str) -> float:
    """Coerce a factor/penalty rating to a float in [0, 5]; raise on out-of-range.

    ValueError (not a bug) so the SignalScore safe_fetch wrapper treats a
    malformed scorecard as a graceful external error, not a crash."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be a number from 0 to 5") from None
    if number < 0 or number > 5:
        raise ValueError(f"{label} must be from 0 to 5; got {number}")
    return number


def score_card(data: dict[str, Any]) -> dict[str, Any]:
    """Score a serenity bottleneck thesis. `data` carries `factors` (8 ratings
    0-5) and optional `penalties` (8 ratings 0-5). Returns the final score, the
    verdict tier, and the per-factor / per-penalty point breakdown."""
    factors = data.get("factors", {})
    penalties = data.get("penalties", {})

    factor_details: dict[str, dict[str, float]] = {}
    factor_total = 0.0
    for key, weight in WEIGHTS.items():
        rating = _num_0_to_5(factors.get(key, 0), f"factors.{key}")
        points = rating / 5.0 * weight
        factor_details[key] = {"rating": rating, "weight": weight, "points": round(points, 2)}
        factor_total += points

    penalty_total = 0.0
    for key in PENALTY_KEYS:
        if key in penalties:
            penalty_total += _num_0_to_5(penalties[key], f"penalties.{key}") * PENALTY_MULTIPLIER

    final_score = max(0.0, min(100.0, factor_total - penalty_total))

    if final_score >= 85:
        verdict = "Top research priority"
    elif final_score >= 70:
        verdict = "High research priority"
    elif final_score >= 55:
        verdict = "Worth tracking"
    else:
        verdict = "Early lead or low priority"

    return {
        "final_score": round(final_score, 2),
        "verdict": verdict,
        "raw_factor_points": round(factor_total, 2),
        "penalty_points": round(penalty_total, 2),
        "factor_details": factor_details,
    }


def score_to_z(final_score: float) -> float:
    """Map a [0, 100] bottleneck score to a clipped z-tilt (see module header)."""
    z = (float(final_score) - _Z_CENTER) / _Z_SCALE
    return max(-_Z_CLIP, min(_Z_CLIP, z))
