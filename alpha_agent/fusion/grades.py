"""Per-dimension letter grades, cross-sectionally re-standardized (2026-06-01).

Original B8 (2026-05-19) mapped each signal's stored "z" through one fixed
z -> letter table (A = z>=1.0). That silently assumed every signal is a true
cross-sectional z-score with std~1. In production only `factor` (Momentum)
actually is: technicals tops out near 0.65 across the whole universe, options
near 0.91, and insider / political / geopolitical / premarket / calendar /
earnings are flat constants (not yet ingested). So only Momentum reached the A
range and multi-signal dimensions, diluted by their dead members, pinned at
C+/C. See the diagnosis in the 2026-06-01 session.

Fix, in three parts:
  1. Drop dead member signals. A signal with no cross-sectional spread across
     the universe (constant, e.g. political_impact, premarket, macro, calendar,
     earnings, insider today) carries zero information, so it is excluded from
     its dimension's value. This removes the "news / 3" style dilution.
  2. Re-standardize each dimension cross-sectionally. The dimension value (mean
     of its LIVE present members) is converted to a z against the universe mean
     and std of that dimension, then graded by the original absolute z bands.
     Momentum is essentially unchanged (factor was already ~N(0,1)); technicals
     and options now spread across the full A-to-F range.
  3. Honest "—" (rule 9, no fake signal). A dimension with no live member, or
     no universe spread, is not gradeable (all-zero Insider / Catalyst today)
     and shows the "—" placeholder, not a meaningless C+.

Re-z (not percentile ranking) is deliberate: many real signals are sparse with
a neutral point mass (most stocks have no material news), and percentile
ranking would dishonestly stretch that neutral mass across A-to-F. Re-z keeps
the neutral mass at the neutral grade and reserves A+/F for genuine outliers.

Dimension -> signal mapping (read alongside fusion.weights.DEFAULT_WEIGHTS):
  Momentum   : factor
  Technical  : technicals
  Sentiment  : news + political_impact + geopolitical_impact
  Catalyst   : earnings + calendar
  Insider    : insider
  Flow       : options + premarket + macro
"""
from __future__ import annotations

from collections import defaultdict
from statistics import mean, pstdev
from typing import Mapping, Sequence

# Dimension grouping. Keys are user-facing labels, values are the contributing
# backend signal names. A signal omitted here feeds no dimension grade.
DIMENSION_GROUPS: dict[str, tuple[str, ...]] = {
    "Momentum": ("factor",),
    "Technical": ("technicals",),
    "Sentiment": ("news", "political_impact", "geopolitical_impact"),
    "Catalyst": ("earnings", "calendar"),
    "Insider": ("insider",),
    "Flow": ("options", "premarket", "macro"),
}

# Placeholder shown when a dimension is not gradeable (no data / no spread).
# Em dash U+2014, matched verbatim by the frontend ribbon.
NO_GRADE = "—"

# Absolute z bands (descending; first satisfied wins, below the last -> "F").
# These are the original B8 thresholds, now applied to a re-standardized z so
# every gradeable dimension shares Momentum's distribution.
_Z_BANDS: tuple[tuple[float, str], ...] = (
    (1.5, "A+"),
    (1.0, "A"),
    (0.5, "B"),
    (0.0, "C+"),
    (-0.5, "C"),
    (-1.0, "D"),
)

# A signal/dimension flatter than this across the universe is treated as a
# constant carrying no cross-sectional information (not gradeable).
_LIVE_STD_FLOOR = 1e-6
# Minimum cross-sectional observations to trust a signal/dimension's stats.
_MIN_UNIVERSE = 20

# Threshold value per gradeable dimension: (live member signals, mean, std).
DimensionStat = tuple[tuple[str, ...], float, float]


def _z_to_letter(z: float) -> str:
    for cut, label in _Z_BANDS:
        if z >= cut:
            return label
    return "F"


def _signal_z_map(
    breakdown: Sequence[Mapping[str, object]],
) -> dict[str, float]:
    """{signal: z} for entries that carry a numeric z."""
    out: dict[str, float] = {}
    for entry in breakdown:
        name = entry.get("signal")
        z = entry.get("z")
        if isinstance(name, str) and isinstance(z, (int, float)):
            out[name] = float(z)
    return out


def compute_dimension_thresholds(
    breakdowns: Sequence[Sequence[Mapping[str, object]]],
) -> dict[str, DimensionStat | None]:
    """Cross-sectional (live members, mean, std) per dimension over the universe.

    A dimension is None (shown "—") when none of its member signals vary across
    the universe, or its own value distribution has no spread.
    """
    maps = [_signal_z_map(bd) for bd in breakdowns]

    # Which signals actually vary cross-sectionally (the rest are constants).
    sig_values: dict[str, list[float]] = defaultdict(list)
    for m in maps:
        for s, z in m.items():
            sig_values[s].append(z)
    live_signals = {
        s
        for s, xs in sig_values.items()
        if len(xs) >= _MIN_UNIVERSE and pstdev(xs) >= _LIVE_STD_FLOOR
    }

    out: dict[str, DimensionStat | None] = {}
    for dim, signals in DIMENSION_GROUPS.items():
        live = tuple(s for s in signals if s in live_signals)
        if not live:
            out[dim] = None
            continue
        vals = []
        for m in maps:
            present = [m[s] for s in live if s in m]
            if present:
                vals.append(sum(present) / len(present))
        if len(vals) < _MIN_UNIVERSE:
            out[dim] = None
            continue
        sd = pstdev(vals)
        if sd < _LIVE_STD_FLOOR:
            out[dim] = None
            continue
        out[dim] = (live, mean(vals), sd)
    return out


def grade_dimensions(
    breakdown: Sequence[Mapping[str, object]],
    thresholds: Mapping[str, DimensionStat | None],
) -> dict[str, str]:
    """Grade one ticker against universe thresholds. NO_GRADE when the dimension
    is not gradeable universe-wide, or this ticker has no live member present."""
    m = _signal_z_map(breakdown)
    out: dict[str, str] = {}
    for dim in DIMENSION_GROUPS:
        th = thresholds.get(dim)
        if th is None:
            out[dim] = NO_GRADE
            continue
        live, mu, sd = th
        present = [m[s] for s in live if s in m]
        if not present:
            out[dim] = NO_GRADE
            continue
        v = sum(present) / len(present)
        out[dim] = _z_to_letter((v - mu) / sd)
    return out
