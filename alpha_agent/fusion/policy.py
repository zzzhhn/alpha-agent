# alpha_agent/fusion/policy.py
"""Explicit, versioned weight policy consumed by live fusion.

Council audit (2026-06-17) item #1: production weighting was an implicit,
unversioned DEFAULT_WEIGHTS constant referenced directly inside the crons,
while a separate adaptive-weight subsystem wrote signal_weight_current that
NOTHING live consumed. That severed live ratings from any governed, auditable
policy. This module makes the live policy a first-class, versioned object that
both crons consume, and that every RatingCard can stamp for auditability.

It deliberately does NOT wire the raw adaptive weights into production (council
item #6 — adaptive stays shadow-only until the IC pipeline + horizon metadata
are fixed and promotion goes through guarded shrinkage). The active policy is
`static_v1`: the hand-set DEFAULT_WEIGHTS, 5d horizon, coverage-aware missing
policy.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from alpha_agent.fusion.weights import DEFAULT_WEIGHTS


@dataclass(frozen=True)
class WeightPolicy:
    """A versioned, auditable fusion policy.

    policy_id:      stable identifier stamped onto every card built with it.
    mode:           static | adaptive_shadow | adaptive_guarded (only `static`
                    governs production today; the others are reserved for the
                    guarded-shrinkage rollout).
    horizon:        the forward horizon this weight set is meant for ("5d").
                    Signals operate at different native horizons; this records
                    what the policy is tuned/validated against.
    weights:        signal_name -> weight.
    core_signals:   the always-expected signal set used to compute coverage.
                    Sparse/optional signals (insider, options, premarket,
                    supply_chain) are NOT core: their absence is bonus-missing,
                    not a conviction penalty (council item #2 missing-type
                    distinction, v1).
    missing_policy: "coverage_sqrt" (damp composite by sqrt(core coverage)) or
                    "renormalize" (legacy: silently redistribute to survivors).
    caps:           per-signal guardrail caps (council item #5). A capped
                    signal's effective weight is scaled DOWN to the cap and the
                    freed weight is NOT redistributed to survivors (it goes to
                    neutral, reducing conviction). Empty = no caps.
    source:         provenance note.
    """

    policy_id: str
    mode: str
    horizon: str
    weights: Mapping[str, float]
    core_signals: tuple[str, ...]
    missing_policy: str
    source: str
    caps: Mapping[str, float] = field(default_factory=dict)

    def core_set(self) -> set[str]:
        return set(self.core_signals)

    def caps_dict(self) -> dict[str, float]:
        return dict(self.caps)


# The always-expected market/fundamental signals. Excludes the sparse ones
# (insider: most names have no recent Form 4; options: not all have liquid
# chains; premarket: only meaningful in the premarket window; supply_chain:
# only the ~10 researched names) and the weight-0 display-only signals.
_CORE_SIGNALS: tuple[str, ...] = (
    "factor",
    "technicals",
    "analyst",
    "earnings",
    "news",
    "macro",
)

# Uncapped baseline. Kept as the explicit prior for the guarded-shrinkage
# shadow (council #6) and as the policy to revert to once the technicals
# guardrail clears its diagnostics.
STATIC_V1 = WeightPolicy(
    policy_id="static_v1",
    mode="static",
    horizon="5d",
    weights=dict(DEFAULT_WEIGHTS),
    core_signals=_CORE_SIGNALS,
    missing_policy="coverage_sqrt",
    source="hand-set DEFAULT_WEIGHTS + serenity supply_chain (0.05 exploratory)",
)

# Council item #5: technicals carries 0.20 live weight but shows materially
# negative observed 5d rank IC. Its native horizon IS 5d (so this is not a
# horizon-mismatch artifact), but the IC sample is still short (~16 non-
# overlapping windows), so this is a CONSERVATIVE, REVERSIBLE guardrail: halve
# the weight (0.20 -> 0.10) rather than zero it. The freed 0.10 is NOT
# reallocated (it goes to neutral, reducing conviction on technicals-driven
# cards). Revert to static_v1 once the sign-flip / component-IC diagnostics and
# more native-horizon IC history clear technicals.
_TECHNICALS_GUARDRAIL_CAP = 0.10

STATIC_V2 = WeightPolicy(
    policy_id="static_v2_technicals_guardrail",
    mode="static",
    horizon="5d",
    weights=dict(DEFAULT_WEIGHTS),
    core_signals=_CORE_SIGNALS,
    missing_policy="coverage_sqrt",
    caps={"technicals": _TECHNICALS_GUARDRAIL_CAP},
    source="static_v1 + council #5 technicals guardrail (cap 0.20->0.10, reversible)",
)


def get_active_policy() -> WeightPolicy:
    """Return the policy that governs live production ratings.

    Single source of truth: both fast_intraday and slow_daily call this instead
    of referencing DEFAULT_WEIGHTS directly, so the live weighting is explicit,
    versioned, and swappable without touching cron code.
    """
    return STATIC_V2
