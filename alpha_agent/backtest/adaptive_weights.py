# alpha_agent/backtest/adaptive_weights.py
"""Phase 1b hardened adaptive weighting.

Pure math (EWMA-ICIR, change-cap, floor/hard-drop) plus a DB orchestrator
that writes shadow candidates, backtests them against the live baseline, and
promotes/rolls-back via config_change_log. Replaces the raw mean(IC) rule.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta

import numpy as np

from alpha_agent.backtest.ic_engine import _MIN_OBS, _spearman_rho

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


async def composite_ic(
    pool, weights: dict[str, float], window_days: int, fwd_days: int = 5
) -> float | None:
    """Spearman IC of the weighted-sum composite signal vs the forward
    `fwd_days`-trading-day return, over recent (ticker, as_of) points.

    The composite per (ticker, as_of) is sum(weights[signal] * z) across that
    row's breakdown; the forward return comes from daily_prices via the same
    LEAD(close, 5) the per-signal IC uses. Returns None below _MIN_OBS points
    or if Spearman is degenerate.
    """
    now = datetime.now(UTC)
    window_start = (now - timedelta(days=window_days)).date()
    fwd_cutoff = (now - timedelta(days=fwd_days)).date()
    rows = await pool.fetch(
        """
        WITH sig AS (
            SELECT f.ticker, f.date AS as_of,
                   elem->>'signal' AS signal_name,
                   (elem->>'z')::double precision AS z
            FROM daily_signals_fast f
            CROSS JOIN LATERAL jsonb_array_elements(f.breakdown->'breakdown') AS elem
            WHERE f.date >= $1 AND f.date <= $2 AND (elem->>'z') IS NOT NULL
        ),
        fwd AS (
            SELECT ticker, date, close AS ce,
                   LEAD(close, 5) OVER (PARTITION BY ticker ORDER BY date) AS cx
            FROM daily_prices
        )
        SELECT s.ticker, s.as_of, s.signal_name, s.z,
               (fwd.cx / fwd.ce - 1)::double precision AS fwd_5d
        FROM sig s
        JOIN fwd ON fwd.ticker = s.ticker AND fwd.date = s.as_of
        WHERE fwd.ce > 0 AND fwd.cx IS NOT NULL
        """,
        window_start, fwd_cutoff,
    )
    comp: dict[tuple, float] = defaultdict(float)
    fwd_ret: dict[tuple, float] = {}
    for r in rows:
        key = (r["ticker"], r["as_of"])
        comp[key] += weights.get(r["signal_name"], 0.0) * float(r["z"])
        fwd_ret[key] = float(r["fwd_5d"])
    if len(comp) < _MIN_OBS:
        return None
    keys = list(comp)
    comp_vals = [comp[k] for k in keys]
    fwd_vals = [fwd_ret[k] for k in keys]
    if np.std(comp_vals) < 1e-9:
        # Constant composite (e.g. all weights zero for present signals):
        # no predictive content; Spearman is undefined.
        return None
    rho = _spearman_rho(comp_vals, fwd_vals)
    if rho is None or np.isnan(rho):
        return None
    return float(rho)


DEGRADE_TOL: float = 0.05  # live composite IC may dip this far below baseline before rollback


async def _gather_icir(pool, signal_name: str, windows=(30, 60, 90)) -> float | None:
    """Mean of per-window EWMA-ICIR over signal_ic_history; None if no window
    has >= 2 points (insufficient history for a risk ratio)."""
    icirs = []
    for w in windows:
        rows = await pool.fetch(
            "SELECT computed_at, ic FROM signal_ic_history "
            "WHERE signal_name=$1 AND window_days=$2 ORDER BY computed_at",
            signal_name, w,
        )
        v = compute_ewma_icir([(r["computed_at"], float(r["ic"])) for r in rows])
        if v is not None:
            icirs.append(v)
    return float(np.mean(icirs)) if icirs else None


async def _weights_by_status(pool, status: str) -> dict[str, float]:
    rows = await pool.fetch(
        "SELECT signal_name, weight FROM signal_weight_current WHERE status=$1", status
    )
    return {r["signal_name"]: float(r["weight"]) for r in rows}


async def _promote(pool, weights: dict[str, float], baseline_ic, now, reason: str) -> None:
    """Copy candidate weights into the live rows and journal the change so a
    later degradation can roll back to the prior live weights."""
    prev = await _weights_by_status(pool, "live")
    for sig, w in weights.items():
        await pool.execute(
            "INSERT INTO signal_weight_current (signal_name, status, weight, last_updated, reason) "
            "VALUES ($1,'live',$2,$3,$4) "
            "ON CONFLICT (signal_name, status) DO UPDATE SET "
            "weight=EXCLUDED.weight, last_updated=EXCLUDED.last_updated, reason=EXCLUDED.reason",
            sig, w, now, reason,
        )
    await pool.execute(
        "INSERT INTO config_change_log (user_id, field, old_value, new_value, source) "
        "VALUES (0, 'signal_weights', $1, $2, $3)",
        json.dumps(prev),
        json.dumps({"weights": weights, "baseline_ic": baseline_ic}),
        reason,
    )


async def _maybe_rollback(pool) -> bool:
    """If the current live composite IC has fallen more than DEGRADE_TOL below
    the baseline_ic recorded at the last promotion, restore that promotion's
    prior weights and journal a rollback_of row. Cold-start seeds (baseline_ic
    is None) are never rolled back."""
    row = await pool.fetchrow(
        """
        SELECT id, old_value, new_value FROM config_change_log
        WHERE field = 'signal_weights' AND source IN ('auto_promote', 'cold_start_seed')
          AND id NOT IN (
            SELECT rollback_of FROM config_change_log WHERE rollback_of IS NOT NULL
          )
        ORDER BY id DESC LIMIT 1
        """
    )
    if row is None:
        return False
    baseline_ic = json.loads(row["new_value"]).get("baseline_ic")
    if baseline_ic is None:
        return False
    live_w = await _weights_by_status(pool, "live")
    live_ic = await composite_ic(pool, live_w, 90)
    # Conservative: a None live IC means we cannot measure degradation (either
    # too few observations, or a degenerate constant composite). Do NOT roll
    # back on an unmeasurable IC, otherwise transient early-life data sparsity
    # (< _MIN_OBS) would trigger spurious rollbacks. Only a measurably-lower
    # composite IC than the baseline justifies reverting.
    if live_ic is None or live_ic >= baseline_ic - DEGRADE_TOL:
        return False
    prev = json.loads(row["old_value"])
    now = datetime.now(UTC)
    for sig, w in prev.items():
        await pool.execute(
            "INSERT INTO signal_weight_current (signal_name,status,weight,last_updated,reason) "
            "VALUES ($1,'live',$2,$3,'auto_rollback') "
            "ON CONFLICT (signal_name,status) DO UPDATE SET "
            "weight=EXCLUDED.weight, last_updated=EXCLUDED.last_updated, reason=EXCLUDED.reason",
            sig, w, now,
        )
    await pool.execute(
        "INSERT INTO config_change_log (user_id, field, old_value, new_value, source, rollback_of) "
        "VALUES (0,'signal_weights',$1,$2,'auto_rollback',$3)",
        json.dumps(live_w), json.dumps(prev), row["id"],
    )
    return True


async def apply_adaptive_weights(pool, active_signals) -> dict:
    """Daily adaptive-weight step: rollback check, candidate -> shadow, then
    promote shadow -> live once it holds non-degrading for SHADOW_PROMOTE_STREAK
    days. On a cold start (no live rows) the candidate seeds live directly."""
    now = datetime.now(UTC)
    rolled_back = await _maybe_rollback(pool)

    # Global cold start = the table has no live rows at all (first-ever run).
    # Only then do we skip the change-cap: capping from current=0 collapses
    # every candidate to the same min-step (CAP_MIN_REF * CHANGE_CAP_FRAC)
    # regardless of ICIR, which would erase the relative ranking we are seeding.
    # A NEW signal added later (others already live) is NOT a global cold start,
    # so it ramps gradually from 0 via the cap rather than jumping to an
    # uncapped weight.
    is_cold_start = (await pool.fetchval(
        "SELECT count(*) FROM signal_weight_current WHERE status='live'"
    )) == 0

    for sig in active_signals:
        icir = await _gather_icir(pool, sig)
        raw_target = max(icir, 0.0) * ICIR_NORMALIZE if icir is not None else 0.0
        live = await pool.fetchrow(
            "SELECT weight, consecutive_bad_windows FROM signal_weight_current "
            "WHERE signal_name=$1 AND status='live'",
            sig,
        )
        cur_w = float(live["weight"]) if live else 0.0
        cur_cb = int(live["consecutive_bad_windows"]) if live else 0
        floored, new_cb, _dropped = apply_floor_or_drop(raw_target, icir, cur_cb)
        capped = floored if is_cold_start else apply_change_cap(cur_w, floored)
        await pool.execute(
            "INSERT INTO signal_weight_current "
            "(signal_name, status, weight, last_updated, reason, consecutive_bad_windows, shadow_streak) "
            "VALUES ($1,'shadow',$2,$3,'shadow_candidate',$4, "
            "COALESCE((SELECT shadow_streak FROM signal_weight_current WHERE signal_name=$1 AND status='shadow'),0)) "
            "ON CONFLICT (signal_name, status) DO UPDATE SET "
            "weight=EXCLUDED.weight, last_updated=EXCLUDED.last_updated, "
            "consecutive_bad_windows=EXCLUDED.consecutive_bad_windows",
            sig, capped, now, new_cb,
        )

    live_w = await _weights_by_status(pool, "live")
    shadow_w = await _weights_by_status(pool, "shadow")
    if not live_w:
        await _promote(pool, shadow_w, baseline_ic=None, now=now, reason="cold_start_seed")
        await pool.execute("UPDATE signal_weight_current SET shadow_streak=0 WHERE status='shadow'")
        return {
            "promoted": True, "reason": "cold_start",
            "ic_live": None, "ic_shadow": None, "rolled_back": rolled_back,
        }

    ic_live = await composite_ic(pool, live_w, 90)
    ic_shadow = await composite_ic(pool, shadow_w, 90)
    promoted = False
    if ic_shadow is not None and (ic_live is None or ic_shadow >= ic_live):
        await pool.execute("UPDATE signal_weight_current SET shadow_streak=shadow_streak+1 WHERE status='shadow'")
        streak = await pool.fetchval("SELECT min(shadow_streak) FROM signal_weight_current WHERE status='shadow'")
        if streak is not None and streak >= SHADOW_PROMOTE_STREAK:
            await _promote(pool, shadow_w, baseline_ic=ic_shadow, now=now, reason="auto_promote")
            await pool.execute("UPDATE signal_weight_current SET shadow_streak=0 WHERE status='shadow'")
            promoted = True
    else:
        await pool.execute("UPDATE signal_weight_current SET shadow_streak=0 WHERE status='shadow'")
    return {"promoted": promoted, "ic_live": ic_live, "ic_shadow": ic_shadow, "rolled_back": rolled_back}
