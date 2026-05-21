# alpha_agent/backtest/adaptive_weights.py
"""Phase 1b hardened adaptive weighting.

Pure math (EWMA-ICIR, change-cap, floor/hard-drop) plus a DB orchestrator
that writes shadow candidates, backtests them against the live baseline, and
promotes/rolls-back via config_change_log. Replaces the raw mean(IC) rule.
"""
from __future__ import annotations

from datetime import date, datetime

import numpy as np

# Tuning constants (Phase 1b decisions 2026-05-21).
HALF_LIFE_DAYS: float = 30.0    # slow EWMA: weights track stable predictive power
CHANGE_CAP_FRAC: float = 0.15   # a weight moves <= 15% of its reference per update
CAP_MIN_REF: float = 0.05       # reference floor so a 0-weight signal can re-grow
WEIGHT_FLOOR: float = 0.02      # diversification floor: a bad window shrinks here
MAX_BAD_WINDOWS: int = 3        # hard-drop to 0 only after this many consecutive bads
ICIR_NORMALIZE: float = 0.10    # scales positive ICIR into the familiar weight range
SHADOW_PROMOTE_STREAK: int = 5  # trading days a candidate must hold before promotion


def compute_ewma_icir(
    points: list[tuple[date | datetime, float]],
    half_life_days: float = HALF_LIFE_DAYS,
) -> float | None:
    """Exponentially-weighted IC information ratio = EWMA-mean(IC) / EWMA-std(IC).

    `points` is (timestamp, ic) for one signal+window in any order. Returns
    None if fewer than 2 points or the weighted std is ~0 (no risk-adjusted
    signal). Newer points get exponentially more weight (half-life in days).
    """
    if len(points) < 2:
        return None
    # Normalize every timestamp to a date up front: callers mix datetime (DB
    # timestamptz `computed_at`) and date (tests), and date-vs-datetime compares
    # raise TypeError in sort/subtraction. Age is computed in whole days anyway,
    # so coercing datetime -> date is lossless here.
    norm = [
        (ts.date() if isinstance(ts, datetime) else ts, float(ic))
        for ts, ic in points
    ]
    pts = sorted(norm, key=lambda p: p[0])
    latest = pts[-1][0]
    lam = 0.5 ** (1.0 / half_life_days)
    ws, ics = [], []
    for ts, ic in pts:
        age = (latest - ts).days
        ws.append(lam ** age)
        ics.append(float(ic))
    w = np.array(ws)
    x = np.array(ics)
    wsum = w.sum()
    mean = float((w * x).sum() / wsum)
    var = float((w * (x - mean) ** 2).sum() / wsum)
    std = var ** 0.5
    if std < 1e-9:
        return None
    return mean / std


def apply_change_cap(
    current: float, target: float, cap_frac: float = CHANGE_CAP_FRAC
) -> float:
    """Clamp `target` so it moves at most `cap_frac` of the reference weight
    away from `current`. The reference is max(|current|, CAP_MIN_REF) so a
    dropped (0-weight) signal can still re-grow slowly instead of being stuck."""
    max_step = cap_frac * max(abs(current), CAP_MIN_REF)
    lo, hi = current - max_step, current + max_step
    return float(min(max(target, lo), hi))


def apply_floor_or_drop(
    raw_target: float,
    icir: float | None,
    consecutive_bad: int,
    floor: float = WEIGHT_FLOOR,
    max_bad: int = MAX_BAD_WINDOWS,
) -> tuple[float, int, bool]:
    """Diversification floor with hard-drop hysteresis.

    A bad window (icir is None or <= 0) shrinks the signal toward `floor`
    rather than to a hard zero, incrementing the consecutive-bad counter; only
    after `max_bad` consecutive bad windows does the weight hard-drop to 0. A
    good window (icir > 0) keeps the positive raw target and resets the counter.
    Returns (weight, new_consecutive_bad, dropped).
    """
    bad = icir is None or icir <= 0
    if not bad:
        return float(raw_target), 0, False
    cb = consecutive_bad + 1
    if cb >= max_bad:
        return 0.0, cb, True
    return float(floor), cb, False
