"""Per-dimension letter grade derivation (B8, 2026-05-19).

Phase 3 backlog item B8. Source: synthesizer T12 — SeekingAlpha
Quant Ratings A+ to F per dimension UI template. Critical adaptation:
SeekingAlpha's dimensions (Value / Growth / Profitability /
Momentum / EPS Revisions) would force monthly fundamental ingest
and trigger the long-only mega-cap-bull-hostility memory; we map
instead to alpha-agent's actual signal groupings so the letter
grades reflect the same horizon as the rest of the composite.

Dimension → signal mapping (read alongside fusion.weights.DEFAULT_WEIGHTS):
  Momentum   : factor                                  (long-horizon
                                                        in LONG mode,
                                                        short in SHORT)
  Technical  : technicals                              (RSI/MACD/MA50/200)
  Sentiment  : news + political_impact + geopolitical  (24h-7d window)
  Catalyst   : earnings + calendar                     (event-driven)
  Insider    : insider                                 (SEC Form 4 30d)
  Flow       : options + premarket + macro             (positioning)

Grade rubric (cross-sectional z-score → letter):
  A+ : z ≥ +1.5    (top decile, strong positive signal)
  A  : z ≥ +1.0
  B  : z ≥ +0.5
  C+ : z ≥  0.0    (above-neutral)
  C  : z ≥ -0.5    (around-neutral)
  D  : z ≥ -1.0
  F  : z <  -1.0   (bottom decile, strong negative signal)

The thresholds align with map_to_tier's BUY/OW/HOLD/UW/SELL bands so a
BUY-rated ticker tends to show ≥3 dimensions at B or better.
"""
from __future__ import annotations

from typing import Mapping, Sequence

# Dimension grouping — keys are the user-facing labels, values are the
# backend signal names that contribute. A signal omitted from this map
# does not appear in any dimension grade (e.g. "calendar" alone is too
# narrow; it shows under Catalyst alongside earnings).
DIMENSION_GROUPS: dict[str, tuple[str, ...]] = {
    "Momentum": ("factor",),
    "Technical": ("technicals",),
    "Sentiment": ("news", "political_impact", "geopolitical_impact"),
    "Catalyst": ("earnings", "calendar"),
    "Insider": ("insider",),
    "Flow": ("options", "premarket", "macro"),
}


def grade_z(z: float | None) -> str:
    """Map a z-score (or None for missing) to an A+/A/B/C+/C/D/F letter."""
    if z is None:
        return "—"
    if z >= 1.5:
        return "A+"
    if z >= 1.0:
        return "A"
    if z >= 0.5:
        return "B"
    if z >= 0.0:
        return "C+"
    if z >= -0.5:
        return "C"
    if z >= -1.0:
        return "D"
    return "F"


def compute_dimension_grades(
    breakdown: Sequence[Mapping[str, object]],
) -> dict[str, str]:
    """Aggregate signal z-scores into per-dimension letter grades.

    Each dimension's z = mean of its contributing signals' z (skipping
    signals absent from the breakdown or with z=None). Empty dimensions
    return "—" so the UI ribbon shows a placeholder cell rather than
    breaking the row width.
    """
    z_by_signal: dict[str, float] = {}
    for entry in breakdown:
        name = entry.get("signal")
        z = entry.get("z")
        if isinstance(name, str) and isinstance(z, (int, float)):
            z_by_signal[name] = float(z)

    out: dict[str, str] = {}
    for dim, signals in DIMENSION_GROUPS.items():
        zs = [z_by_signal[s] for s in signals if s in z_by_signal]
        if not zs:
            out[dim] = "—"
            continue
        mean_z = sum(zs) / len(zs)
        out[dim] = grade_z(mean_z)
    return out
