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
from alpha_agent.brain.fastexpr import generate_brain_candidates
from alpha_agent.brain.logic_screen import score_economic_logic, select_by_logic
from alpha_agent.brain.tuning import base_settings_for, diagnose, retry_variant
from alpha_agent.evolution.correlation_gate import (
    incremental_contribution,
    max_corr_against,
)


async def _simulate_one(client: BrainClient, expr: str, settings: dict, timeout_s: float):
    """Simulate one expression with one settings dict → (alpha_id, metrics).
    Raises on sim failure / missing alpha id (caller buckets it as sim_error)."""
    sim_id = await client.simulate(expr, settings)
    sim = await client.poll_simulation(sim_id, max_wait_s=timeout_s)
    alpha_id = sim.get("alpha")
    if not alpha_id:
        raise BrainSimulationError("completed sim carried no alpha id")
    return alpha_id, await client.get_alpha_metrics(alpha_id)

# WorldQuant's SELF_CORRELATION bar: a new alpha correlating this much with an
# existing ACTIVE one (on daily returns) is a re-discovery, not new alpha.
_SELF_CORR_THRESHOLD = 0.7
# G1: a passer must add at least this fraction of NOVEL variance (1 - R^2) on top
# of its nearest accepted-basket neighbours. Deliberately low (0.15) so it flags
# only the clearly-spanned (the pairwise gate missed collective low-rank), NOT
# merely-correlated good factors — keeping the pass rate healthy.
_MARGINAL_MIN = 0.15


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
    seed_from_user_alphas: bool = True,
    logic_llm=None,
    max_retries: int = 12,
) -> dict:
    """Execute one round and return a bucket summary. Every candidate's outcome
    is persisted to brain_alphas regardless of pass/fail so the UI + the next
    round have the full picture.

    Seeding: unless explicit `seed_exprs` are given, the GA breeds from the
    user's OWN existing alphas (the golden templates) so it explores around
    proven structures instead of random noise. The BRAIN self-correlation gate
    (authoritative) then flags any offspring that ends up too close to an
    existing alpha — so seeding improves hit-rate without producing un-submittable
    near-duplicates."""
    await client.authenticate()
    existing = await _existing_active_returns(client)

    if seed_exprs is None and seed_from_user_alphas:
        try:
            seed_exprs = await client.fetch_alpha_expressions(limit=200)
            print(f"[seed] {len(seed_exprs or [])} of the user's own alphas", flush=True)
        except Exception:  # noqa: BLE001 — seeding is best-effort
            seed_exprs = None

    # Fetch BRAIN's REAL data-fields (fundamentals/analyst included) so the
    # generator's golden templates use fields that actually clear the Sharpe/
    # Fitness bars — not just OHLCV. Falls back to base price fields on failure.
    real_fields: Optional[list[str]] = None
    try:
        real_fields = await client.fetch_data_fields(limit=500)
        print(f"[fields] {len(real_fields or [])} real BRAIN data-fields", flush=True)
    except Exception:  # noqa: BLE001 — best-effort; base fields still work
        real_fields = None

    # Phase F3 self-evolution: read the mining history and steer this round away
    # from homogenization — skip already-mined structures, prefer under-used
    # economic ratios, rotate neutralization to INDUSTRY when self-correlation is
    # running high. Best-effort: empty state → no steering.
    from alpha_agent.brain.evolution import load_evolution_state

    evo = await load_evolution_state(pool, user_id)
    if evo.avoid_signatures:
        print(
            f"[evolve] avoiding {len(evo.avoid_signatures)} past structures; "
            f"flagged_rate={evo.flagged_rate:.2f} prefer_industry={evo.prefer_industry}",
            flush=True,
        )

    # Over-generate so the logic screen has candidates to prune down to
    # n_candidates worth of economically-sensible ones.
    gen_n = n_candidates * 2 if logic_llm is not None else n_candidates
    import os
    family_focus = os.environ.get("BRAIN_FAMILY_FOCUS") or None
    if family_focus:
        print(f"[focus] family-constrained round: {family_focus}", flush=True)
    candidates = generate_brain_candidates(
        gen_n, seed_exprs=seed_exprs, fields=real_fields, rng_seed=rng_seed,
        ratio_usage=evo.ratio_usage, prefer_industry=evo.prefer_industry,
        avoid_signatures=evo.avoid_signatures, family_focus=family_focus,
    )

    # LLM financial-logic pre-screen (AlphaEval 'Financial Logic'): score the
    # candidates' economic sense in one batched call and simulate only the
    # sensible ones — BRAIN sims are the bottleneck, so not wasting them on
    # nonsense raises hit-rate. No-op without an LLM client.
    if logic_llm is not None:
        scores = await score_economic_logic(logic_llm, candidates)
        candidates = select_by_logic(candidates, scores)[:n_candidates]
        print(f"[logic] screened to {len(candidates)} sensible candidates", flush=True)
    summary = {
        "generated": len(candidates),
        "passed": 0,
        "flagged": 0,
        "rejected": 0,
        "sim_error": 0,
    }

    # The diverse set a new PASS must stay decorrelated from: the user's ACTIVE
    # alphas + their recent PASSED-but-unsubmitted mined alphas + this round's own
    # accepted passers. BRAIN's SELF_CORRELATION check only sees ACTIVE alphas, so
    # a batch of near-identical candidates all score ~0 there and all "pass" — but
    # submitting one pushes the rest over the 0.7 bar. We compute the intra-set
    # correlation locally (on daily returns) to keep the passed set genuinely
    # diverse. Best-effort: any load failure just means fewer references.
    accepted_returns: dict[str, np.ndarray] = dict(existing)
    # `our_passed` is the subset that is OURS (mined, passed, not yet submitted) —
    # these are the rows whose self-correlation we reconcile at round end. `existing`
    # (active alphas) are references only; we never rewrite their rows.
    our_passed: dict[str, np.ndarray] = {}
    try:
        prior = await store.recent_passed_unsubmitted_alpha_ids(pool, user_id, limit=40)
    except Exception:  # noqa: BLE001 — empty/absent history is fine
        prior = []
    for aid in prior:
        try:
            r = pnl_to_daily_returns(await client.get_pnl(aid))
        except Exception:  # noqa: BLE001 — one bad alpha must not abort the round
            continue
        if r is not None:
            accepted_returns[aid] = r
            our_passed[aid] = r
    if prior:
        print(f"[diversity] {len(accepted_returns)} reference series (active + prior passed)", flush=True)

    # One timestamp for the whole round, from the DB clock (same anchor the
    # progress counter uses), so every row this round shares a batch id the UI
    # can group on and show on the batch divider. Best-effort: None just means
    # these rows fall into the "legacy" group and draw no divider.
    try:
        batch_started_at = await pool.fetchval("SELECT now()")
    except Exception:  # noqa: BLE001 — batch tagging is cosmetic, never abort a round
        batch_started_at = None

    retry_budget = max_retries
    for expr in candidates:
        # Family-adaptive BASE settings (fast/technical signals get more decay).
        settings = base_settings_for(expr)
        did_retry = False
        try:
            alpha_id, metrics = await _simulate_one(client, expr, settings, sim_timeout_s)
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
                batch_started_at=batch_started_at,
            )
            summary["sim_error"] += 1
            continue

        # Smart retry: a NEAR-miss on a settings-fixable check gets ONE targeted
        # re-simulation (bounded per round via retry_budget). If the variant clears
        # the gate it replaces the base result, and the WINNING settings are what
        # we store — so the review UI shows the config that actually worked.
        if not metrics.passes_gates() and retry_budget > 0:
            variant = retry_variant(settings, diagnose(metrics))
            if variant is not None:
                retry_budget -= 1
                did_retry = True
                try:
                    aid2, m2 = await _simulate_one(client, expr, variant, sim_timeout_s)
                    if m2.passes_gates():
                        alpha_id, metrics, settings = aid2, m2, variant
                        print(
                            f"[tune] fixed {expr[:44]!r} "
                            f"decay={variant.get('decay')} universe={variant.get('universe')} "
                            f"trunc={variant.get('truncation')}",
                            flush=True,
                        )
                except Exception:  # noqa: BLE001 — a failed retry just keeps the base
                    pass

        common = dict(
            user_id=user_id, expression=expr, settings=settings, alpha_id=alpha_id,
            sharpe=metrics.sharpe, fitness=metrics.fitness,
            turnover=metrics.turnover, drawdown=metrics.drawdown,
            returns=metrics.returns, margin=metrics.margin, grade=metrics.grade,
            retried=did_retry, batch_started_at=batch_started_at,
        )

        if not metrics.passes_gates():
            await store.record_brain_alpha(
                pool, **common, outcome="rejected",
                fail_checks=",".join(metrics.failing_checks()) or None,
                detail="below in-sample gates",
            )
            summary["rejected"] += 1
            continue

        # TWO self-correlations, stored side by side:
        #   OFFICIAL  = BRAIN's own SELF_CORRELATION vs the user's ACTIVE alphas
        #               (is.checks first — free — then /correlations/self). None if
        #               BRAIN hasn't computed one (e.g. no active alphas yet).
        #   ADJUSTED  = our local corr vs `accepted_returns` (active + passed-but-
        #               unsubmitted + THIS round's passers) — counts the successful
        #               factors BRAIN can't see because they aren't submitted. This
        #               is the only source that catches a batch of mutual near-dups.
        # The gate flags on the MAX of the two.
        official = metrics.brain_self_correlation()
        if official is None:
            official = await client.get_self_correlation(alpha_id)
        official_with = "BRAIN" if official is not None else None

        cand_rets = None
        try:
            cand_rets = pnl_to_daily_returns(await client.get_pnl(alpha_id))
        except Exception:  # noqa: BLE001 — no PnL just means no local diversity signal
            cand_rets = None
        adj, adj_with = 0.0, None
        if cand_rets is not None and accepted_returns:
            adj, adj_with = max_corr_against(cand_rets, accepted_returns)

        corr_kw = dict(
            self_correlation=official, self_correlation_with=official_with,
            self_correlation_adj=adj, self_correlation_adj_with=adj_with,
        )

        # G1 basket-orthogonality gate. Pairwise self-corr passes a batch that is
        # collectively low-rank (each member <0.7 yet the set jointly spans a tiny
        # subspace — the real homogenization escape). Require the candidate to add
        # genuine variance ON TOP of the accepted basket: 1 - R^2 of its daily
        # returns regressed on its 8 nearest basket neighbours. Best-effort → 1.0
        # (fully novel) when unmeasurable, so it can only ever flag MORE, never
        # fewer, than the pairwise gate.
        marginal, marginal_with = (
            incremental_contribution(cand_rets, accepted_returns, k=8)
            if cand_rets is not None and accepted_returns
            else (1.0, None)
        )

        too_correlated = max(official or 0.0, adj) >= _SELF_CORR_THRESHOLD
        too_redundant = marginal < _MARGINAL_MIN
        if too_correlated or too_redundant:
            reason = (
                f"self-corr official={official} adj={adj:.2f} vs {adj_with}"
                if too_correlated
                else f"low marginal contribution {marginal:.2f} "
                f"(<{_MARGINAL_MIN}) — spanned by basket ({marginal_with})"
            )
            print(
                f"[flag] {expr[:44]!r} corr={adj:.2f} marginal={marginal:.2f} "
                f"({'corr' if too_correlated else 'redundant'})",
                flush=True,
            )
            await store.record_brain_alpha(
                pool, **common, **corr_kw, outcome="flagged", detail=reason,
            )
            summary["flagged"] += 1
            continue

        # Passed → joins the accepted diverse set, so later candidates in the round
        # (and future rounds, via the DB) must stay decorrelated from it too.
        if cand_rets is not None:
            accepted_returns[alpha_id] = cand_rets
            our_passed[alpha_id] = cand_rets
        await store.record_brain_alpha(
            pool, **common, **corr_kw, outcome="passed",
        )
        summary["passed"] += 1

    # Reconcile the ADJUSTED self-correlation across the FULL passed-but-unsubmitted
    # set so an early passer's value reflects factors mined after it (otherwise
    # frozen at mining time). Returns are already in memory — no extra BRAIN calls.
    # The OFFICIAL column is left as BRAIN reported it.
    for aid, rets in our_passed.items():
        others = {k: v for k, v in accepted_returns.items() if k != aid}
        if not others:
            continue
        corr, corr_with = max_corr_against(rets, others)
        try:
            await store.update_adjusted_self_correlation(
                pool, user_id, aid, value=corr, corr_with=corr_with
            )
        except Exception:  # noqa: BLE001 — reconciliation is best-effort
            pass

    return summary
