"""Phase E3: FASTEXPR alpha generator for the BRAIN miner.

Reuses the local GA's tree genetics (ga_dsl) with a BRAIN-specific Vocab — the
operators map 1:1 to FASTEXPR, only the field/group alphabet differs. On BRAIN
the fitness function IS the platform's simulate, so this is pure diverse
generation: seed with known-good alphas, mutate/crossover for local diversity,
gate on the grammar, dedupe. Phase E4's loop simulates these on BRAIN and keeps
the ones that clear the metric gates."""
from __future__ import annotations

import random
from typing import Optional

from alpha_agent.brain.client import DEFAULT_SETTINGS
from alpha_agent.core.factor_ast import expression_to_tree, validate_expression
from alpha_agent.evolution import ga_dsl

# Fields valid in BOTH BRAIN FASTEXPR and the local grammar (_ALLOWED_OPERANDS),
# so validate_expression can gate them. subindustry first — highest sim pass rate.
BRAIN_VOCAB = ga_dsl.Vocab(
    fields=(
        "close", "open", "high", "low", "volume",
        "returns", "vwap", "cap", "adv20", "adv60",
    ),
    groups=("subindustry", "industry", "sector"),
    windows=(5, 10, 20, 40, 60, 120),
    params=(2, 3, 4),
)

# BRAIN gates operators by user level ("inaccessible or unknown operator" — a
# base account can't use the more advanced ones; run #1 proved ts_max is gated).
# Restrict generation to the operators documented as working in the BRAIN SKILL,
# and drop any candidate that uses one outside this set. Trim further if a future
# run's sim_error details surface more gated ops.
BRAIN_SAFE_OPS = frozenset({
    "add", "subtract", "multiply", "divide",
    "rank", "zscore", "normalize", "scale", "sign", "log", "abs", "sqrt",
    "inverse", "winsorize",
    "ts_mean", "ts_std_dev", "ts_sum", "ts_delta", "ts_delay",
    "ts_rank", "ts_zscore", "ts_decay_linear", "ts_corr",
    "group_rank", "group_zscore", "group_neutralize",
})


def brain_settings(*, decay: int = 0, neutralization: str = "SUBINDUSTRY") -> dict:
    """A per-candidate simulation settings dict. decay controls turnover
    (fundamental 0, technical 10-30); subindustry neutralization passes most."""
    return {**DEFAULT_SETTINGS, "decay": decay, "neutralization": neutralization}


def generate_brain_candidates(
    n: int,
    *,
    rng_seed: int = 1234,
    seed_exprs: Optional[list[str]] = None,
    max_depth: int = 4,
) -> list[str]:
    """Produce n distinct, grammar-valid FASTEXPR expressions over BRAIN_VOCAB
    for BRAIN to simulate. Seeds (known-good alphas / the current live factor)
    join the pool and are mutated/crossed for local diversity; generated trees
    feed back so later candidates explore around promising ones."""
    rng = random.Random(rng_seed)
    pool: list[dict] = []
    for expr in seed_exprs or ():
        try:
            pool.append(expression_to_tree(expr))
        except Exception:  # noqa: BLE001 — a bad seed just doesn't join the pool
            continue

    seen: set[str] = set()
    out: list[str] = []
    guard = 0
    while len(out) < n and guard < n * 50:
        guard += 1
        if pool and rng.random() < 0.55:
            a = rng.choice(pool)
            if len(pool) >= 2 and rng.random() < 0.5:
                tree = ga_dsl.mutate(
                    rng, ga_dsl.crossover(rng, a, rng.choice(pool)), BRAIN_VOCAB
                )
            else:
                tree = ga_dsl.mutate(rng, a, BRAIN_VOCAB)
        else:
            tree = ga_dsl.random_tree(rng, max_depth, BRAIN_VOCAB)

        if ga_dsl.tree_depth(tree) > max_depth:
            continue
        expr = ga_dsl.tree_to_expression(tree)
        if expr in seen:
            continue
        ops = ga_dsl.used_operators(tree)
        if not ops:  # skip a bare field leaf — nothing for BRAIN to score
            continue
        if any(op not in BRAIN_SAFE_OPS for op in ops):
            continue  # skip level-gated operators BRAIN would reject
        try:
            validate_expression(expr, ops)
        except Exception:  # noqa: BLE001 — drop invalid/degenerate (e.g. x-x, x/x)
            continue
        seen.add(expr)
        out.append(expr)
        pool.append(tree)  # feed winners back so search explores around them
    return out
