# alpha_agent/fusion/combine.py
"""Weighted composite + breakdown attribution.

Two call styles supported (backward compat):

  Legacy (pre-Phase-6a):
      combine(signals: Mapping[str, SignalScore], weights: Mapping[str, float])
        -> CombineResult

      The caller passes a dict of SignalScore objects plus an explicit weights
      mapping (typically DEFAULT_WEIGHTS from alpha_agent.fusion.weights).

  Phase 6a (dynamic DB-driven weights):
      combine(breakdown_in: list[dict], weights_override: dict[str, float])
        -> dict {"composite_score": float, "breakdown": [...]}

      Used by the cron pipeline after `load_weights(pool)` reads the current
      weight per signal from the `signal_weight_current` DB table (written by
      the monthly walk-forward IC backtest engine in T7).

Both styles share the same drop logic:
  1. confidence == 0       (signal said "I have no data")
  2. weight == 0           (e.g. calendar display-only, or auto-dropped by IC)
  3. z is NaN/Inf          (signal lied about confidence; treat as no-info)

Effective weights are re-normalized across the surviving signals.
0-weight survivors are surfaced in the breakdown with weight_effective=0 so
the frontend can render a grayed-out state.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping

from alpha_agent.signals.base import SignalScore
from alpha_agent.fusion.weights import DEFAULT_WEIGHTS, normalize_weights


@dataclass
class CombineResult:
    composite: float
    breakdown: list[dict[str, Any]] = field(default_factory=list)
    # Council item #2 (coverage-aware fusion): fraction of CORE signal weight
    # actually present (1.0 = full core coverage). None when coverage-aware
    # fusion was not requested (legacy survivor-renormalize behavior).
    coverage: float | None = None


def _core_coverage(
    weights: Mapping[str, float],
    drop: set[str],
    core: set[str],
) -> float:
    """Fraction of CORE signal weight present (not dropped).

    Coverage measures whether the always-expected market/fundamental signals
    are available; sparse/optional signals are excluded from `core` so their
    structural absence does not penalize conviction. Returns 1.0 when no core
    signal carries weight (nothing to be missing)."""
    total = sum(w for n, w in weights.items() if n in core and w > 0)
    if total <= 0:
        return 1.0
    present = sum(
        w for n, w in weights.items() if n in core and w > 0 and n not in drop
    )
    return present / total


async def load_weights(pool) -> dict[str, float]:
    """Read current per-signal weights from `signal_weight_current`.

    Only rows with status='live' are returned; shadow candidate rows are
    excluded so they cannot leak into live fusion and corrupt the composite.

    Returns {signal_name: weight} for live rows. If no live rows exist
    (cold start before the first monthly IC backtest run), falls back to
    DEFAULT_WEIGHTS so the cron pipeline still produces a composite.
    """
    rows = await pool.fetch(
        "SELECT signal_name, weight FROM signal_weight_current WHERE status = 'live'"
    )
    if not rows:
        return dict(DEFAULT_WEIGHTS)
    return {r["signal_name"]: float(r["weight"]) for r in rows}


def _is_finite_number(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _apply_caps(
    eff: dict[str, float],
    weights: Mapping[str, float],
    caps: Mapping[str, float] | None,
) -> dict[str, float]:
    """Scale a capped signal's effective weight down to its cap, WITHOUT
    redistributing the freed weight to other signals (council #5: a guardrailed
    signal's excess weight goes to neutral, reducing conviction, rather than
    inflating the survivors). No-op when caps is empty. Returns a new dict."""
    if not caps:
        return eff
    out = dict(eff)
    for name, cap in caps.items():
        w = weights.get(name, 0.0)
        if name in out and w > 0 and cap < w:
            out[name] = out[name] * (cap / w)
    return out


def _combine_breakdown_list(
    breakdown_in: list[dict[str, Any]],
    weights: Mapping[str, float],
    coverage_core: set[str] | None = None,
    caps: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """New-style: list of breakdown dicts in, dict envelope out."""
    drop: set[str] = set()
    for entry in breakdown_in:
        name = entry["signal"]
        conf = entry.get("confidence", 0.0)
        z = entry.get("z")
        w = weights.get(name, 0.0)
        if conf == 0.0:
            drop.add(name)
        if w == 0:
            drop.add(name)
        if not _is_finite_number(z):
            drop.add(name)

    eff = normalize_weights(weights, drop=drop)
    eff = _apply_caps(eff, weights, caps)
    composite = 0.0
    breakdown_out: list[dict[str, Any]] = []
    for entry in breakdown_in:
        name = entry["signal"]
        z = entry.get("z")
        w_orig = weights.get(name, 0.0)
        w_eff = eff.get(name, 0.0)
        if w_eff == 0:
            contribution = 0.0
        else:
            contribution = float(z) * w_eff
        composite += contribution
        out = dict(entry)
        out["weight"] = w_orig
        out["weight_effective"] = w_eff
        out["contribution"] = contribution
        breakdown_out.append(out)
    coverage = None
    if coverage_core is not None:
        coverage = _core_coverage(weights, drop, coverage_core)
        composite *= math.sqrt(coverage)
    return {
        "composite_score": composite,
        "breakdown": breakdown_out,
        "coverage": coverage,
    }


def _combine_signal_mapping(
    signals: Mapping[str, SignalScore],
    weights: Mapping[str, float],
    coverage_core: set[str] | None = None,
    caps: Mapping[str, float] | None = None,
) -> CombineResult:
    """Legacy-style: {name: SignalScore} in, CombineResult out."""
    drop = {n for n, sc in signals.items() if sc["confidence"] == 0.0}
    drop |= {n for n, w in weights.items() if w == 0}
    drop |= {
        n for n, sc in signals.items()
        if not _is_finite_number(sc["z"])
    }
    eff = normalize_weights(weights, drop=drop)
    eff = _apply_caps(eff, weights, caps)
    composite = 0.0
    breakdown: list[dict[str, Any]] = []
    for name, sc in signals.items():
        w_orig = weights.get(name, 0.0)
        w_eff = eff.get(name, 0.0)
        # Force contribution to 0 when signal is dropped, regardless of z
        # (NaN x 0 = NaN in Python, which would poison composite).
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
    coverage = None
    if coverage_core is not None:
        coverage = _core_coverage(weights, drop, coverage_core)
        composite *= math.sqrt(coverage)
    return CombineResult(
        composite=composite, breakdown=breakdown, coverage=coverage
    )


def combine(
    signals_or_breakdown,
    weights: Mapping[str, float] | None = None,
    *,
    weights_override: Mapping[str, float] | None = None,
    coverage_core: set[str] | None = None,
    caps: Mapping[str, float] | None = None,
):
    """Compute weighted composite + per-signal breakdown.

    Dispatches on input shape:
      * list -> new-style (Phase 6a dynamic-weight path). Returns dict.
      * Mapping[str, SignalScore] -> legacy path. Returns CombineResult.

    Weight resolution priority:
      1. weights_override (kwarg, used by Phase 6a cron after load_weights)
      2. weights (positional, legacy call sites passing DEFAULT_WEIGHTS)
      3. DEFAULT_WEIGHTS fallback (so legacy callers that forgot weights
         still get a sensible default)
    """
    resolved_weights: Mapping[str, float]
    if weights_override is not None:
        resolved_weights = weights_override
    elif weights is not None:
        resolved_weights = weights
    else:
        resolved_weights = DEFAULT_WEIGHTS

    if isinstance(signals_or_breakdown, list):
        return _combine_breakdown_list(
            signals_or_breakdown, resolved_weights,
            coverage_core=coverage_core, caps=caps,
        )
    return _combine_signal_mapping(
        signals_or_breakdown, resolved_weights,
        coverage_core=coverage_core, caps=caps,
    )
