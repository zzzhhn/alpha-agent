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
    pts = sorted(points, key=lambda p: p[0])
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
