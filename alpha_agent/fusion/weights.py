# alpha_agent/fusion/weights.py
"""Default fusion weights + redistribution helper.

Weights are now derived from the single signal registry (the source of truth
for signal identity); see alpha_agent/signals/registry.py for the per-signal
rationale (technicals trimmed to fund rsrs; supply_chain/geopolitical
exploratory). NB: the total is 1.05, not 1.0 (supply_chain added without a
compensating trim); combine() renormalizes over contributing signals so this is
harmless, flagged for the re-tune step."""
from __future__ import annotations

from typing import Mapping

from alpha_agent.signals.registry import default_weights as _default_weights

# Derived from SIGNAL_REGISTRY (one source of truth). A signal-identity drift
# test (tests/signals/test_signal_registry.py) pins these exact values.
DEFAULT_WEIGHTS: dict[str, float] = _default_weights()


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
