# alpha_agent/backtest/confidence_calibration.py
"""Phase 1c confidence calibration.

Measures realized directional hit-rate per stated confidence (reliability
curve + Brier), fits a monotone isotonic map (numpy PAVA, no sklearn), and
applies it on the live read path to suppress overconfidence only. The daily
cron appends a fresh calibration row; the read path loads the latest.
"""
from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timedelta

import numpy as np

MIN_PAIRS: int = 50          # below this, fall back to identity (no recalibration)
FIT_WINDOW_DAYS: int = 90    # rolling fit window; uses all available if < this
_FWD_DAYS: int = 5
_UP_TIERS = frozenset({"BUY", "OW"})
_DOWN_TIERS = frozenset({"UW", "SELL"})


def _hit(rating: str, fwd_5d: float) -> bool | None:
    """True/False if the rating's directional call matched the realized
    forward 5-day return sign; None for HOLD (excluded from calibration).
    Pure sign match, no deadband: a non-positive return fails an up-call."""
    if rating in _UP_TIERS:
        return fwd_5d > 0
    if rating in _DOWN_TIERS:
        return fwd_5d < 0
    return None


async def gather_confidence_hits(pool, window_days: int = FIT_WINDOW_DAYS) -> list[tuple[float, int]]:
    """Return [(stated_confidence, hit01), ...] over the rolling window: each
    non-HOLD daily_signals_fast row with an observable 5-trading-day forward
    return (from daily_prices) contributes one pair. hit01 is 1/0."""
    now = datetime.now(UTC)
    window_start = (now - timedelta(days=window_days)).date()
    fwd_cutoff = (now - timedelta(days=_FWD_DAYS)).date()
    rows = await pool.fetch(
        """
        WITH fwd AS (
            SELECT ticker, date, close AS ce,
                   LEAD(close, 5) OVER (PARTITION BY ticker ORDER BY date) AS cx
            FROM daily_prices
        )
        SELECT f.rating, f.confidence,
               (fwd.cx / fwd.ce - 1)::double precision AS fwd_5d
        FROM daily_signals_fast f
        JOIN fwd ON fwd.ticker = f.ticker AND fwd.date = f.date
        WHERE f.date >= $1 AND f.date <= $2
          AND f.rating IS NOT NULL AND f.confidence IS NOT NULL
          AND fwd.ce > 0 AND fwd.cx IS NOT NULL
        """,
        window_start, fwd_cutoff,
    )
    pairs: list[tuple[float, int]] = []
    for r in rows:
        h = _hit(r["rating"], float(r["fwd_5d"]))
        if h is None:
            continue
        pairs.append((float(r["confidence"]), 1 if h else 0))
    return pairs


def _pava(y) -> np.ndarray:
    """Pool-adjacent-violators isotonic regression (non-decreasing), equal
    weights. Returns the fitted values aligned to the input order."""
    vals: list[float] = []
    cnts: list[int] = []
    for v in y:
        vals.append(float(v))
        cnts.append(1)
        while len(vals) > 1 and vals[-2] > vals[-1]:
            v2, c2 = vals.pop(), cnts.pop()
            v1, c1 = vals.pop(), cnts.pop()
            cn = c1 + c2
            vals.append((v1 * c1 + v2 * c2) / cn)
            cnts.append(cn)
    out: list[float] = []
    for v, c in zip(vals, cnts):
        out.extend([v] * c)
    return np.array(out)


def isotonic_fit(pairs: list[tuple[float, int]]) -> dict | None:
    """Fit a monotone non-decreasing confidence -> hit-rate map via PAVA.
    Returns {"x": [...], "y": [...]} breakpoints (strictly increasing x), or
    None if fewer than MIN_PAIRS samples (identity fallback upstream)."""
    if len(pairs) < MIN_PAIRS:
        return None
    arr = sorted(pairs, key=lambda p: p[0])
    xs = np.array([p[0] for p in arr], dtype=float)
    ys = np.array([float(p[1]) for p in arr], dtype=float)
    fitted = _pava(ys)
    # Collapse to unique x (np.interp needs strictly increasing x). The fitted
    # value is constant within a pooled block, so the mean over a tied x is exact.
    ux = np.unique(xs)
    uy = np.array([float(fitted[xs == x].mean()) for x in ux])
    return {"x": ux.tolist(), "y": uy.tolist()}


def apply_calibration(raw_confidence: float, cal_map: dict | None) -> float:
    """Suppress overconfidence only: calibrated = min(isotonic(raw), raw).
    Identity when there is no usable map (None / empty), so a thin or missing
    calibration never inflates a displayed confidence."""
    raw = float(raw_confidence)
    if not cal_map:
        return raw
    xs, ys = cal_map.get("x"), cal_map.get("y")
    if not xs or not ys:
        return raw
    mapped = float(np.interp(raw, xs, ys))
    return min(mapped, raw)


def reliability_and_brier(pairs: list[tuple[float, int]], n_buckets: int = 10) -> list[dict]:
    """Bucket pairs by stated confidence into n_buckets equal-width [0,1] bins;
    per bucket report realized hit_rate, Brier (mean (confidence - hit)^2), and
    count. Empty buckets are reported with n=0 so the reliability curve is dense."""
    edges = np.linspace(0.0, 1.0, n_buckets + 1)
    out: list[dict] = []
    confs = np.array([p[0] for p in pairs], dtype=float)
    hits = np.array([p[1] for p in pairs], dtype=float)
    for i in range(n_buckets):
        lo, hi = float(edges[i]), float(edges[i + 1])
        # last bucket is closed on the right so confidence == 1.0 lands somewhere.
        in_bin = (confs >= lo) & (confs < hi) if i < n_buckets - 1 else (confs >= lo) & (confs <= hi)
        n = int(in_bin.sum())
        if n == 0:
            out.append({"lo": lo, "hi": hi, "hit_rate": None, "brier": None, "n": 0})
            continue
        c_in, h_in = confs[in_bin], hits[in_bin]
        out.append({
            "lo": lo, "hi": hi,
            "hit_rate": float(h_in.mean()),
            "brier": float(np.mean((c_in - h_in) ** 2)),
            "n": n,
        })
    return out


async def run_calibration(pool) -> dict:
    """Gather (confidence, hit) pairs over the rolling window, fit the isotonic
    map, compute the reliability/Brier diagnostics, and append a row to
    confidence_calibration. `applied` is False when below MIN_PAIRS (the map is
    stored as empty so the loader treats it as identity)."""
    pairs = await gather_confidence_hits(pool)
    cal_map = isotonic_fit(pairs)
    buckets = reliability_and_brier(pairs)
    applied = cal_map is not None
    await pool.execute(
        "INSERT INTO confidence_calibration (as_of, isotonic_map, buckets, n_pairs, applied) "
        "VALUES (now(), $1::jsonb, $2::jsonb, $3, $4)",
        json.dumps(cal_map or {"x": [], "y": []}),
        json.dumps(buckets),
        len(pairs), applied,
    )
    return {"n_pairs": len(pairs), "applied": applied}


# Process-local memo for the active calibration map. The map only changes when
# the daily cron appends a new row, so reading it on every request was a wasted
# DB round trip — costly when the function (hkg1) and DB (us-east-1) sit in
# different regions. A few-minute staleness is harmless (calibration is daily).
# Freshness is keyed on `ts` alone so a legitimate None value (identity, no
# usable map) is still cached rather than re-queried every request.
_CAL_TTL_SECONDS = 600.0
_cal_cache: dict = {"ts": None, "val": None}


async def load_active_calibration(pool) -> dict | None:
    """Most recent APPLIED calibration map, or None (identity) if none exists.
    Read on the live path and passed to apply_calibration. Memoized in-process
    for a few minutes (see _cal_cache above)."""
    now = time.monotonic()
    if _cal_cache["ts"] is not None and (now - _cal_cache["ts"]) < _CAL_TTL_SECONDS:
        return _cal_cache["val"]
    row = await pool.fetchrow(
        "SELECT isotonic_map FROM confidence_calibration "
        "WHERE applied = true ORDER BY as_of DESC LIMIT 1"
    )
    if row is None:
        val = None
    else:
        m = json.loads(row["isotonic_map"])
        val = m if m.get("x") else None
    _cal_cache["val"] = val
    _cal_cache["ts"] = now
    return val
