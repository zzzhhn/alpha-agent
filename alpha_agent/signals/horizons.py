# alpha_agent/signals/horizons.py
"""Native horizon metadata per signal (council 2026-06-17 item #4).

The fusion engine and the IC backtest historically treated every signal on a
single 5-day forward horizon, which is horizon-incoherent: factor is a
long-horizon cross-sectional signal, premarket is intraday, supply_chain is a
multi-month thesis. Judging a 60-day signal by its 5-day rank IC understates
it and can wrongly trigger a hard-drop.

This registry records each signal's NATIVE forward horizon (trading days) so
the backtest can validate each signal at the horizon it actually operates on
(in addition to a common 5d tactical reference for cross-signal comparison),
and so the UI can label what a signal's score is really predicting.

These are first-pass horizons grounded in each signal's mechanism; they are
meant to be refined once the per-horizon IC matrix accumulates enough history.
"""
from __future__ import annotations

# signal_name -> native forward horizon in TRADING days.
SIGNAL_HORIZON_DAYS: dict[str, int] = {
    "factor": 60,           # cross-sectional factor exposure, long-horizon
    "technicals": 5,        # multi-day momentum / moving-average structure
    "analyst": 20,          # rating/target revisions play out over weeks
    "earnings": 20,         # post-earnings drift
    "news": 3,              # sentiment decays fast
    "insider": 20,          # Form 4 cluster signal is multi-week
    "options": 5,           # put/call + IV skew, multi-day
    "premarket": 1,         # overnight gap, intraday horizon
    "macro": 20,            # rate/vol regime shifts over weeks
    "calendar": 5,          # display-only
    "political_impact": 5,  # display-only / event proximity
    "geopolitical_impact": 5,  # display-only / policy-action proximity
    "supply_chain": 60,     # bottleneck thesis is a multi-month view
}

# Reference horizon used as a common cross-signal comparison + the default for
# legacy callers that do not pass a horizon. Matches the prior hardcoded 5d.
DEFAULT_HORIZON_DAYS: int = 5


def native_horizon(signal_name: str) -> int:
    """Return the signal's native forward horizon (trading days), or the
    default reference horizon when the signal is not registered."""
    return SIGNAL_HORIZON_DAYS.get(signal_name, DEFAULT_HORIZON_DAYS)
