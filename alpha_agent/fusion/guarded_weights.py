"""Guarded activation of the adaptive weights (roadmap step 5 / council #6).

The adaptive EWMA-ICIR subsystem (backtest/adaptive_weights.py) writes
signal_weight_current, but the live crons fused on the STATIC policy weights and
ignored it — an inert subsystem (false capability), which the council forbids.
This module activates it SAFELY: live fusion uses

    effective[s] = (1 - alpha) * static[s] + alpha * adaptive[s]

with a SMALL alpha (0.10) and hard guards:
  - min-sample gate: a signal is pulled toward adaptive only if it has >= MIN_OBS
    IC observations (else it stays at its static prior);
  - fallback: a signal with no adaptive 'live' row stays at its static prior;
  - non-negative clamp;
  - per-signal caps are applied DOWNSTREAM by combine() (the active policy's
    caps_dict), so they are not duplicated here.

Net effect: on a cold / test DB with no adaptive rows, the effective weights
equal the static weights EXACTLY, so activation can only ever nudge live ratings
within a bounded band, never lurch onto noisy free-data IC. Light module (no
numpy / pandas) so the live cron path stays cheap.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime

# Adaptive pull. The council's guarded-activation ceiling: 10% toward evidence,
# 90% anchored to the hand-set prior.
GUARDED_ALPHA: float = 0.10

# A signal needs at least this many IC observations (5d reference horizon)
# before its adaptive estimate is trusted enough to pull the live weight.
_MIN_OBS_DEFAULT: int = 10

# ── Inversion guard (2026-07-05) ────────────────────────────────────────────
# The guarded blend can only SHRINK a signal by alpha per step (10% toward
# evidence, 90% anchored to the prior), so a dimension whose realized IC turns
# PERSISTENTLY NEGATIVE keeps ~90% of its hand-set weight and drags the whole
# composite below zero — measured live 2026-07-05: options/technicals/earnings/
# news all negative 30d rolling IC, composite 5d IC -0.03, long-short spread
# INVERTED (-4.6% over 21d). The guard zeroes such a dimension outright until
# its IC recovers; combine() renormalizes across the survivors, so the
# positive-IC dimensions automatically pick up the freed share.
#
# Deliberately NO sign-flip: flipping a whole dimension is a regime bet that
# whipsaws when the regime mean-reverts. Zeroing is the safe removal of a
# measured-harmful input; recovery is automatic because the guard re-evaluates
# the trailing window on every fusion.
_INV_MEAN_IC_MAX: float = -0.01   # trailing mean IC at/below this ...
_INV_FRAC_NEG_MIN: float = 0.6    # ... with at least this fraction of negative points
_INV_MIN_POINTS: int = 8          # ... over at least this many IC computations
_INV_WINDOW_DAYS: int = 30        # trailing calendar window for the IC points


def inverted_signals_from_series(
    series: dict[str, list[float]],
    *,
    mean_ic_max: float = _INV_MEAN_IC_MAX,
    frac_neg_min: float = _INV_FRAC_NEG_MIN,
    min_points: int = _INV_MIN_POINTS,
) -> set[str]:
    """Pure rule: which signals' trailing IC series read as PERSISTENTLY
    inverted (mean at/below `mean_ic_max` AND >= `frac_neg_min` of points
    negative, over >= `min_points` points). Thin/noisy series never qualify."""
    out: set[str] = set()
    for sig, ics in series.items():
        if len(ics) < min_points:
            continue
        mean = sum(ics) / len(ics)
        frac_neg = sum(1 for v in ics if v < 0) / len(ics)
        if mean <= mean_ic_max and frac_neg >= frac_neg_min:
            out.add(sig)
    return out


async def inverted_signals(pool, *, window_days: int = _INV_WINDOW_DAYS) -> set[str]:
    """Signals whose trailing 5d-horizon IC history is persistently negative."""
    rows = await pool.fetch(
        """
        SELECT signal_name, ic
        FROM signal_ic_history
        WHERE horizon_days = 5
          AND computed_at >= now() - make_interval(days => $1)
        ORDER BY signal_name, computed_at
        """,
        window_days,
    )
    series: dict[str, list[float]] = {}
    for r in rows:
        if r["ic"] is not None:
            series.setdefault(r["signal_name"], []).append(float(r["ic"]))
    return inverted_signals_from_series(series)


async def _log_inversion_changes(
    pool, *, newly_zeroed: set[str], recovered: set[str]
) -> None:
    """Audit trail: one config_change_log row per guard TRANSITION (not per
    fusion), so the evolution UI can annotate the IC chart with WHEN a dimension
    was removed / restored (traceability: show what happened, never invent why).
    Schema (V009): user_id 0 = system, source distinguishes the guard."""
    for sig in sorted(newly_zeroed):
        await pool.execute(
            "INSERT INTO config_change_log "
            "(user_id, field, old_value, new_value, source) "
            "VALUES (0, 'signal_weights', $1, $2, 'inversion_guard')",
            json.dumps({"signal": sig, "state": "active"}),
            json.dumps({"signal": sig, "state": "zeroed",
                        "reason": "persistent negative IC"}),
        )
    for sig in sorted(recovered):
        await pool.execute(
            "INSERT INTO config_change_log "
            "(user_id, field, old_value, new_value, source) "
            "VALUES (0, 'signal_weights', $1, $2, 'inversion_guard')",
            json.dumps({"signal": sig, "state": "zeroed"}),
            json.dumps({"signal": sig, "state": "active",
                        "reason": "IC recovered"}),
        )


def blend_guarded(
    static: dict[str, float],
    adaptive: dict[str, float],
    *,
    eligible: set[str],
    alpha: float = GUARDED_ALPHA,
) -> dict[str, float]:
    """Pure guarded blend. For each static signal: pull toward the adaptive
    estimate by `alpha` IFF it has an adaptive value AND is in `eligible`
    (min-sample gate); otherwise keep the static prior. Clamp non-negative."""
    out: dict[str, float] = {}
    for sig, w in static.items():
        a = adaptive.get(sig)
        if a is not None and sig in eligible:
            out[sig] = max(0.0, (1.0 - alpha) * w + alpha * float(a))
        else:
            out[sig] = float(w)
    return out


async def eligible_signals(pool, *, min_obs: int = _MIN_OBS_DEFAULT) -> set[str]:
    """Signals with >= min_obs IC observations at the 5d reference horizon —
    the min-sample gate for trusting an adaptive estimate."""
    rows = await pool.fetch(
        """
        SELECT signal_name
        FROM signal_ic_history
        WHERE horizon_days = 5
        GROUP BY signal_name
        HAVING count(*) >= $1
        """,
        min_obs,
    )
    return {r["signal_name"] for r in rows}


async def _adaptive_live_weights(pool) -> dict[str, float]:
    rows = await pool.fetch(
        "SELECT signal_name, weight FROM signal_weight_current WHERE status = 'live'"
    )
    return {r["signal_name"]: float(r["weight"]) for r in rows}


async def _persist_effective(pool, effective: dict[str, float]) -> None:
    """Record the effective weights (status='effective') for audit. Idempotent
    upsert; the run ledger can reference these as the weights actually applied."""
    now = datetime.now(UTC)
    for sig, w in effective.items():
        await pool.execute(
            "INSERT INTO signal_weight_current "
            "(signal_name, status, weight, last_updated, reason) "
            "VALUES ($1, 'effective', $2, $3, $4) "
            "ON CONFLICT (signal_name, status) DO UPDATE SET "
            "weight = EXCLUDED.weight, last_updated = EXCLUDED.last_updated, "
            "reason = EXCLUDED.reason",
            sig, w, now, json.dumps({"alpha": GUARDED_ALPHA, "mode": "adaptive_guarded"}),
        )


async def get_effective_weights(
    pool,
    *,
    static: dict[str, float] | None = None,
    alpha: float = GUARDED_ALPHA,
    min_obs: int = _MIN_OBS_DEFAULT,
    persist: bool = True,
) -> dict[str, float]:
    """The weights live fusion should use: the static prior guardedly blended
    with the adaptive estimate. Reads the adaptive 'live' rows + the min-sample
    gate, blends, optionally persists the effective weights for audit.

    Falls back to the active policy's static weights when `static` is None.
    """
    if static is None:
        from alpha_agent.fusion.policy import get_active_policy
        static = dict(get_active_policy().weights)

    adaptive = await _adaptive_live_weights(pool)
    if not adaptive:
        # Nothing promoted yet -> pure static (safe, identical to pre-activation).
        return dict(static)

    elig = await eligible_signals(pool, min_obs=min_obs)
    effective = blend_guarded(static, adaptive, eligible=elig, alpha=alpha)

    # Inversion guard: zero any dimension whose trailing IC is persistently
    # negative (combine() renormalizes across survivors, so the freed share
    # flows to the positive-IC dimensions automatically). State transitions are
    # persisted (status='inversion_guard' rows exist only while zeroed) and
    # logged once per flip — never once per fusion.
    try:
        inverted = await inverted_signals(pool)
        prev_rows = await pool.fetch(
            "SELECT signal_name FROM signal_weight_current "
            "WHERE status = 'inversion_guard'"
        )
        prev = {r["signal_name"] for r in prev_rows}
        inverted &= set(effective)  # only guard signals that exist in this policy
        for sig in inverted:
            effective[sig] = 0.0
        newly = inverted - prev
        recovered = prev - inverted
        if persist and (newly or recovered):
            now = datetime.now(UTC)
            for sig in newly:
                await pool.execute(
                    "INSERT INTO signal_weight_current "
                    "(signal_name, status, weight, last_updated, reason) "
                    "VALUES ($1, 'inversion_guard', 0.0, $2, $3) "
                    "ON CONFLICT (signal_name, status) DO UPDATE SET "
                    "weight = 0.0, last_updated = EXCLUDED.last_updated",
                    sig, now,
                    json.dumps({"mode": "inversion_guard",
                                "rule": "mean_ic<=-0.01 & frac_neg>=0.6 (30d)"}),
                )
            for sig in recovered:
                await pool.execute(
                    "DELETE FROM signal_weight_current "
                    "WHERE signal_name = $1 AND status = 'inversion_guard'",
                    sig,
                )
            await _log_inversion_changes(pool, newly_zeroed=newly, recovered=recovered)
    except Exception:  # noqa: BLE001 — the guard must never break live fusion
        pass

    if persist:
        await _persist_effective(pool, effective)
    return effective
