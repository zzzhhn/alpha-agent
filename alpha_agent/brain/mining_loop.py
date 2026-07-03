"""Phase E4: one BRAIN mining round.

Ties the pieces together: authenticate, read the user's ACTIVE alphas' daily
returns (for self-correlation), generate FASTEXPR candidates (E3), simulate each
on BRAIN, gate on the real in-sample metrics, run the SELF_CORRELATION check on
daily returns, and persist every outcome bucketed passed/flagged/rejected/
sim_error. Never auto-submits — passed/flagged alphas are surfaced for the user.

Runs in a GitHub Actions job (BRAIN simulations poll for minutes, well past any
serverless budget), talking to Neon directly. The loop itself is client- and
pool-injected so it unit-tests against a fake BrainClient with no network."""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

from alpha_agent.brain import store
from alpha_agent.brain.client import BrainClient, BrainSimulationError
from alpha_agent.brain.fastexpr import brain_settings, generate_brain_candidates
from alpha_agent.evolution.correlation_gate import max_corr_against

# WorldQuant's SELF_CORRELATION bar: a new alpha correlating this much with an
# existing ACTIVE one (on daily returns) is a re-discovery, not new alpha.
_SELF_CORR_THRESHOLD = 0.7


def pnl_to_daily_returns(pnl: dict) -> Optional[np.ndarray]:
    """BRAIN PnL recordset (cumulative) → daily-return series. Defensive about
    the exact schema: take the last numeric column of each record and diff it
    (per the SKILL: correlate DAILY returns, never cumulative PnL which inflates
    every correlation > 0.9). None if unparseable, too short, or flat."""
    records = pnl.get("records") if isinstance(pnl, dict) else None
    if not records or len(records) < 4:
        return None
    try:
        cum = np.array([float(r[-1]) for r in records], dtype=np.float64)
    except (TypeError, ValueError, IndexError):
        return None
    daily = np.diff(cum)
    if daily.size < 3 or float(np.nanstd(daily)) < 1e-12:
        return None
    return daily


async def _existing_active_returns(client: BrainClient) -> dict[str, np.ndarray]:
    """Daily returns of every ACTIVE alpha, keyed by id — the set a new
    candidate must not correlate with. Best-effort per alpha."""
    out: dict[str, np.ndarray] = {}
    for alpha in await client.list_active_alphas():
        aid = alpha.get("id")
        if not aid:
            continue
        try:
            rets = pnl_to_daily_returns(await client.get_pnl(aid))
        except Exception:  # noqa: BLE001 — one bad alpha must not abort the round
            continue
        if rets is not None:
            out[aid] = rets
    return out


async def run_mining_round(
    client: BrainClient,
    pool,
    user_id: int,
    *,
    n_candidates: int = 8,
    seed_exprs: Optional[list[str]] = None,
    rng_seed: int = 1234,
    sim_timeout_s: float = 300.0,
) -> dict:
    """Execute one round and return a bucket summary. Every candidate's outcome
    is persisted to brain_alphas regardless of pass/fail so the UI + the next
    round have the full picture."""
    await client.authenticate()
    existing = await _existing_active_returns(client)

    candidates = generate_brain_candidates(
        n_candidates, seed_exprs=seed_exprs, rng_seed=rng_seed
    )
    settings = brain_settings()
    summary = {
        "generated": len(candidates),
        "passed": 0,
        "flagged": 0,
        "rejected": 0,
        "sim_error": 0,
    }

    for expr in candidates:
        try:
            sim_id = await client.simulate(expr, settings)
            sim = await client.poll_simulation(sim_id, max_wait_s=sim_timeout_s)
            alpha_id = sim.get("alpha")
            if not alpha_id:
                raise BrainSimulationError("completed sim carried no alpha id")
            metrics = await client.get_alpha_metrics(alpha_id)
        except Exception as exc:  # noqa: BLE001 — persist + continue the round
            detail = f"{type(exc).__name__}: {exc}"
            # Also log to stdout so the GitHub Actions run surfaces WHY a sim
            # failed without a DB round-trip — a whole round of sim_error is a
            # systematic problem (auth / expr format / endpoint shape), and the
            # detail is the fastest way to see which.
            logger.warning("sim_error for %r: %s", expr[:60], detail)
            print(f"[sim_error] {expr[:60]!r}: {detail}", flush=True)
            await store.record_brain_alpha(
                pool, user_id=user_id, expression=expr, settings=settings,
                outcome="sim_error", detail=detail,
            )
            summary["sim_error"] += 1
            continue

        common = dict(
            user_id=user_id, expression=expr, settings=settings, alpha_id=alpha_id,
            sharpe=metrics.sharpe, fitness=metrics.fitness,
            turnover=metrics.turnover, drawdown=metrics.drawdown,
        )

        if not metrics.passes_gates():
            await store.record_brain_alpha(
                pool, **common, outcome="rejected", detail="below in-sample gates"
            )
            summary["rejected"] += 1
            continue

        self_corr, corr_with = 0.0, None
        try:
            rets = pnl_to_daily_returns(await client.get_pnl(alpha_id))
            if rets is not None and existing:
                self_corr, corr_with = max_corr_against(rets, existing)
        except Exception:  # noqa: BLE001 — no PnL just means no self-corr signal
            pass

        if self_corr >= _SELF_CORR_THRESHOLD:
            await store.record_brain_alpha(
                pool, **common, self_correlation=self_corr,
                self_correlation_with=corr_with, outcome="flagged",
                detail=f"self-corr {self_corr:.2f} vs {corr_with}",
            )
            summary["flagged"] += 1
            continue

        await store.record_brain_alpha(
            pool, **common, self_correlation=self_corr,
            self_correlation_with=corr_with, outcome="passed",
        )
        summary["passed"] += 1

    return summary
