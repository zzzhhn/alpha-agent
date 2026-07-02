"""Phase C: GA loop + panel-backed composite fitness.

Breeds factor expressions with ga_dsl's genetic operators, scoring each with a
single-split kernel evaluation (a cheap OOS proxy — far faster than the LLM
proposer's full purged walk-forward). The top-K survivors are returned for the
SAME DSR-gated validation (evaluate_factor_candidate) that LLM candidates go
through, so the GA is purely a cheaper candidate SOURCE, not a second grader.

The evolve loop is pure (fitness is injected), so it unit-tests without a DB or
kernel; make_kernel_fitness / run_ga_search wire in the real panel."""
from __future__ import annotations

import math
import random
from typing import Callable, Optional

from alpha_agent.evolution import ga_dsl

# Composite fitness weights on the single-split OOS metrics. IC is O(0.01-0.05)
# so it carries a large multiplier to sit on the same scale as Sharpe/ICIR;
# turnover is penalized so the GA doesn't chase churny, cost-fragile signals.
_W_SHARPE, _W_ICIR, _W_IC, _W_TURNOVER = 1.0, 1.5, 5.0, 0.25


def composite_fitness(metrics) -> float:
    """Blend OOS Sharpe + ICIR + IC, penalize turnover. Any non-finite metric
    (degenerate/constant factor) scores -inf so it dies out of the population."""
    vals = (metrics.sharpe, metrics.icir, metrics.ic_spearman, metrics.turnover)
    if any(v is None or math.isnan(v) or math.isinf(v) for v in vals):
        return float("-inf")
    return (
        _W_SHARPE * metrics.sharpe
        + _W_ICIR * metrics.icir
        + _W_IC * metrics.ic_spearman
        - _W_TURNOVER * metrics.turnover
    )


def make_kernel_fitness(
    panel, *, direction: str = "long_short", n_trials: int = 1
) -> Callable[[str], float]:
    """Build a memoized expr -> fitness function over a fixed panel. Validates
    the expression against the real grammar first (so degenerate / invalid
    offspring score -inf), then runs one kernel split and blends its OOS
    metrics. Never raises — an unfit candidate is just -inf."""
    from alpha_agent.core.factor_ast import expression_to_tree, validate_expression
    from alpha_agent.core.types import FactorSpec
    from alpha_agent.factor_engine.kernel import KernelParams, run_kernel

    params = KernelParams(direction=direction, n_trials=n_trials)
    cache: dict[str, float] = {}

    def fitness(expr: str) -> float:
        if expr in cache:
            return cache[expr]
        score = float("-inf")
        try:
            tree = expression_to_tree(expr)
            validate_expression(expr, ga_dsl.used_operators(tree))
            spec = FactorSpec(
                name="ga_candidate",
                hypothesis="ga",
                expression=expr,
                operators_used=[],
                lookback=20,
                universe="SP500",
                justification="ga cheap-fitness probe",
            )
            kr = run_kernel(panel, spec, params)
            score = composite_fitness(kr.test_metrics)
        except Exception:  # noqa: BLE001 — invalid/unfit candidate => -inf, never blocks
            score = float("-inf")
        cache[expr] = score
        return score

    return fitness


def _tournament(rng: random.Random, ranked: list, k: int) -> dict:
    """Pick the fittest of k random contenders; return its tree."""
    contenders = [rng.choice(ranked) for _ in range(k)]
    return max(contenders, key=lambda row: row[2])[0]


def evolve(
    rng: random.Random,
    seeds: list,
    fitness_fn: Callable[[str], float],
    *,
    pop_size: int = 30,
    generations: int = 8,
    elitism: int = 4,
    tournament_k: int = 3,
    max_depth: int = 6,
    budget_s: Optional[float] = None,
    clock: Optional[Callable[[], float]] = None,
    vocab: ga_dsl.Vocab = ga_dsl.DEFAULT_VOCAB,
) -> list[tuple[str, float]]:
    """Run the GA. Returns distinct (expression, best-score) pairs, fittest
    first, with -inf (invalid/unfit) filtered out. Deterministic given `rng`.

    Elitism carries the top few unchanged each generation; the rest are bred by
    tournament-selected crossover + mutation, rejecting offspring past max_depth
    so trees don't bloat. `budget_s` (with an injectable `clock` for tests) caps
    wall-clock — checked between generations."""
    import time

    now = clock or time.monotonic
    deadline = now() + budget_s if budget_s is not None else None

    pop = list(seeds)
    while len(pop) < pop_size:
        pop.append(ga_dsl.random_tree(rng, 3, vocab))
    pop = pop[:pop_size]

    best: dict[str, float] = {}

    def evaluate(trees: list) -> list:
        scored = []
        for t in trees:
            expr = ga_dsl.tree_to_expression(t)
            s = fitness_fn(expr)
            if s > best.get(expr, float("-inf")):
                best[expr] = s
            scored.append((t, expr, s))
        scored.sort(key=lambda row: row[2], reverse=True)
        return scored

    ranked = evaluate(pop)
    for _ in range(generations):
        if deadline is not None and now() > deadline:
            break
        nxt = [row[0] for row in ranked[:elitism]]
        guard = 0
        while len(nxt) < pop_size and guard < pop_size * 20:
            guard += 1
            p1 = _tournament(rng, ranked, tournament_k)
            p2 = _tournament(rng, ranked, tournament_k)
            child = ga_dsl.mutate(rng, ga_dsl.crossover(rng, p1, p2), vocab)
            if ga_dsl.tree_depth(child) <= max_depth:
                nxt.append(child)
        ranked = evaluate(nxt)

    return sorted(
        ((e, s) for e, s in best.items() if s > float("-inf")),
        key=lambda kv: kv[1],
        reverse=True,
    )


def run_ga_search(
    *,
    pop_size: int = 30,
    generations: int = 8,
    top_k: int = 6,
    budget_s: float = 120.0,
    seed_exprs: Optional[list[str]] = None,
    rng_seed: int = 1234,
    direction: str = "long_short",
    n_trials: int = 1,
    vocab: ga_dsl.Vocab = ga_dsl.DEFAULT_VOCAB,
) -> list[str]:
    """End-to-end: load the panel, breed candidates, return the top-K expression
    strings for downstream DSR-gated validation. `seed_exprs` (e.g. the current
    live factor + known-good templates) join the initial population. `vocab`
    restricts the field/window alphabet — the BRAIN miner passes its FASTEXPR
    vocabulary here to reuse this exact search."""
    from alpha_agent.core.factor_ast import expression_to_tree
    from alpha_agent.factor_engine.factor_backtest import _load_panel

    panel = _load_panel()
    fitness = make_kernel_fitness(panel, direction=direction, n_trials=n_trials)
    rng = random.Random(rng_seed)

    seeds: list[dict] = []
    for expr in seed_exprs or ():
        try:
            seeds.append(expression_to_tree(expr))
        except Exception:  # noqa: BLE001 — a bad seed just doesn't join the pool
            continue

    best = evolve(
        rng, seeds, fitness,
        pop_size=pop_size, generations=generations, budget_s=budget_s,
        vocab=vocab,
    )
    return [expr for expr, _score in best[:top_k]]


def ga_candidates(**kwargs) -> list:
    """The GA's top-K expressions wrapped as RawProposals — the exact input type
    evaluate_factor_candidate expects, so GA candidates flow through the SAME
    canned-test + purged walk-forward + DSR gate as the LLM proposer's. GA
    candidates never author operators, so new_operators is always empty. Accepts
    the same kwargs as run_ga_search."""
    from alpha_agent.evolution.llm_factor_proposer import RawProposal

    return [
        RawProposal(
            expression=expr,
            new_operators=[],
            rationale="GA/mutation search (non-LLM generator)",
        )
        for expr in run_ga_search(**kwargs)
    ]
