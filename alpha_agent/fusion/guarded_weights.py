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
    if persist:
        await _persist_effective(pool, effective)
    return effective
