"""Methodology proposer orchestrator (Phase 2a). Enumerate single-knob
candidates, score each on purged walk-forward OOS folds, deflate the best by
the trial count, and queue only the survivors (beat baseline AND post-deflation
positive) as pending config_change_log rows, capped per day. Nothing applies
automatically; Phase 2b is the human approve/reject tier. Dormant (writes
nothing) until enough history exists to validate."""
from __future__ import annotations

import json

import numpy as np

from alpha_agent.config_store import DEFAULTS, get_config, refresh_config
from alpha_agent.evolution.candidates import ConfigDelta, enumerate_candidates
from alpha_agent.evolution.validation import deflated_sharpe_lite, evaluate_candidate

MAX_PROPOSALS_PER_DAY = 3


def _identity_delta(current: dict) -> ConfigDelta:
    """A no-op delta that re-asserts factor.mode's current value so
    evaluate_candidate scores the CURRENT config as the OOS baseline
    without changing anything observable."""
    return ConfigDelta(
        "factor.mode",
        current["factor.mode"],
        "baseline (current config)",
    )


async def run_proposer(pool, user_id: int = 0) -> dict:
    """Enumerate candidates, evaluate each, filter survivors, write pending rows.

    Returns a summary dict:
      {"evaluated": int, "proposed": int, "dormant": bool}

    When history is too short for even the baseline to produce MIN_FOLDS
    usable folds, returns dormant=True and writes nothing.

    Guarantees:
    - Never calls set_config.
    - Never writes to engine_config.
    - _CACHE is clean on return (evaluate_candidate restores per-eval;
      run_proposer itself does not override _CACHE).
    """
    await refresh_config(pool)
    current = {k: get_config(k, DEFAULTS[k]) for k in DEFAULTS}

    base = await evaluate_candidate(pool, _identity_delta(current))
    if base is None:
        return {"evaluated": 0, "proposed": 0, "dormant": True}

    candidates = enumerate_candidates(current)
    results = []
    for c in candidates:
        r = await evaluate_candidate(pool, c)
        if r is not None:
            results.append(r)

    # Deflation denominator is the honest number of configs we TRIED (the full
    # enumerated count), not just the ones that scored. Candidates that returned
    # None still consumed a selection-bias trial; undercounting them would
    # shrink the haircut and flatter the survivors.
    n_trials = len(candidates)
    base_mean = float(np.mean(base.sharpes))
    all_means = [float(np.mean(r.sharpes)) for r in results]

    proposed = 0
    for r in sorted(results, key=lambda r: -float(np.mean(r.sharpes))):
        if proposed >= MAX_PROPOSALS_PER_DAY:
            break
        r_mean = float(np.mean(r.sharpes))
        defl = deflated_sharpe_lite(r_mean, all_means, n_trials)
        if r_mean > base_mean and defl > 0:
            await _write_pending(pool, current, r, defl, n_trials, user_id)
            proposed += 1

    return {"evaluated": len(results), "proposed": proposed, "dormant": False}


async def _write_pending(
    pool,
    current: dict,
    result,
    deflated_sharpe: float,
    n_trials: int,
    user_id: int,
) -> None:
    """Insert a single pending config_change_log row for an approved survivor."""
    delta = result.delta
    old_value = current.get(delta.key)
    evidence = {
        "sharpes": [float(s) for s in result.sharpes],
        "ic_oos": float(result.ic_oos),
        "deflated_sharpe": float(deflated_sharpe),
        "n_trials": int(n_trials),
        "rationale": delta.rationale,
    }
    await pool.execute(
        "INSERT INTO config_change_log "
        "(user_id, field, old_value, new_value, source, status, evidence) "
        "VALUES ($1, $2, $3, $4, 'proposer', 'pending', $5::jsonb)",
        user_id,
        delta.key,
        json.dumps(old_value),
        json.dumps(delta.new_value),
        json.dumps(evidence),
    )
