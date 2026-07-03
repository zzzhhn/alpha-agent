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
from alpha_agent.core.factor_ast import expression_to_tree
from alpha_agent.evolution import ga_dsl

# Base price/volume fields, always valid on BRAIN. When real data-fields are
# fetched (fundamentals/analyst), they're mixed in on top of these.
_BASE_FIELDS = ("close", "open", "high", "low", "volume", "returns", "vwap")

# Fields valid in BOTH BRAIN FASTEXPR and the local grammar (_ALLOWED_OPERANDS),
# so validate_expression can gate them. subindustry first — highest sim pass rate.
BRAIN_VOCAB = ga_dsl.Vocab(
    # Only fields proven valid on BRAIN (these all simulated in earlier rounds).
    # adv20/adv60/dollar_volume/cap were guesses — BRAIN rejected adv60 as an
    # "unknown variable", so they're dropped. Richer fields (fundamentals,
    # analyst) need the BRAIN data-fields API (see fetch note in mining_loop).
    fields=("close", "open", "high", "low", "volume", "returns", "vwap"),
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
    "inverse",
    # winsorize dropped: BRAIN's signature is winsorize(x, std=N) — a NAMED
    # param — but our serializer emits a positional 2nd arg, which BRAIN reads
    # as a 2nd input and rejects ("should be exactly 1 input").
    "ts_mean", "ts_std_dev", "ts_sum", "ts_delta", "ts_delay",
    "ts_rank", "ts_zscore", "ts_decay_linear", "ts_corr",
    "group_rank", "group_zscore", "group_neutralize",
})


def brain_settings(*, decay: int = 0, neutralization: str = "SUBINDUSTRY") -> dict:
    """A per-candidate simulation settings dict. decay controls turnover
    (fundamental 0, technical 10-30); subindustry neutralization passes most."""
    return {**DEFAULT_SETTINGS, "decay": decay, "neutralization": neutralization}


def _build_vocab(fields: Optional[list[str]]) -> ga_dsl.Vocab:
    """Vocab from real BRAIN data-fields (mixed with the always-valid base
    fields), or just the base fields when none were fetched."""
    all_fields = tuple(dict.fromkeys((*_BASE_FIELDS, *(fields or ()))))
    return ga_dsl.Vocab(
        fields=all_fields,
        groups=BRAIN_VOCAB.groups,
        windows=BRAIN_VOCAB.windows,
        params=BRAIN_VOCAB.params,
    )


def _op(name: str, *args: dict) -> dict:
    return {"type": "operator", "name": name, "args": list(args)}


def _fld(name: str) -> dict:
    return {"type": "operand", "name": name}


def _lit(v: int) -> dict:
    return {"type": "literal", "value": v}


# Golden alpha structures (WorldQuant's documented high-pass-rate motifs). Each
# builds a tree from real fields — the cross-sectional group_rank/neutralize over
# a normalized time-series signal is what actually beats the Sharpe/Fitness bars,
# far more than the random price expressions of earlier rounds.
def _golden_template(rng: random.Random, v: ga_dsl.Vocab) -> dict:
    f = lambda: _fld(rng.choice(v.fields))  # noqa: E731
    g = lambda: _fld(rng.choice(v.groups))  # noqa: E731
    w = lambda: _lit(rng.choice(v.windows))  # noqa: E731
    builders = (
        # group_rank(ts_rank(FIELD, W), GROUP) — the canonical golden combo
        lambda: _op("group_rank", _op("ts_rank", f(), w()), g()),
        # group_neutralize(ts_zscore(FIELD, W), GROUP)
        lambda: _op("group_neutralize", _op("ts_zscore", f(), w()), g()),
        # group_rank(divide(FIELD_A, FIELD_B), GROUP) — cross-sectional ratio
        lambda: _op("group_rank", _op("divide", f(), f()), g()),
        # rank(ts_delta(FIELD, W)) — momentum/change
        lambda: _op("rank", _op("ts_delta", f(), w())),
        # group_rank(ts_mean(FIELD, W), GROUP)
        lambda: _op("group_rank", _op("ts_mean", f(), w()), g()),
        # group_zscore(divide(ts_delta(FIELD, W), FIELD), GROUP) — growth rate
        lambda: _op(
            "group_zscore", _op("divide", _op("ts_delta", f(), w()), f()), g()
        ),
        # BLENDED: add two group-ranked signals over different fields. Blending
        # decorrelated stable signals is the documented LOW_FITNESS fix — the
        # single-field fundamentals hit Sharpe>1.25 but missed Fitness (returns
        # too low); a blend raises returns/stability without wrecking Sharpe.
        lambda: _op(
            "add",
            _op("group_rank", _op("ts_rank", f(), w()), _fld("subindustry")),
            _op("group_rank", _op("ts_rank", f(), w()), _fld("subindustry")),
        ),
        # BLENDED ratio + momentum, subindustry-neutral
        lambda: _op(
            "add",
            _op("group_rank", _op("divide", f(), f()), _fld("subindustry")),
            _op("group_rank", _op("ts_delta", f(), w()), _fld("subindustry")),
        ),
    )
    return rng.choice(builders)()


def _degenerate(tree: dict) -> bool:
    """subtract(x, x) / divide(x, x) anywhere — BRAIN rejects these as constants."""
    if tree.get("type") != "operator":
        return False
    if tree["name"] in ("subtract", "divide") and len(tree["args"]) == 2:
        if ga_dsl.tree_to_expression(tree["args"][0]) == ga_dsl.tree_to_expression(
            tree["args"][1]
        ):
            return True
    return any(_degenerate(a) for a in tree["args"])


def _valid_brain_tree(tree: dict) -> Optional[str]:
    """Grammar-free validation for BRAIN generation (the local factor_ast grammar
    can't gate real BRAIN fundamental fields). Returns the expression string if
    the tree is a non-degenerate expression using only BRAIN-safe operators,
    else None."""
    ops = ga_dsl.used_operators(tree)
    if not ops:  # bare field leaf — nothing for BRAIN to score
        return None
    if any(op not in BRAIN_SAFE_OPS for op in ops):
        return None
    if _degenerate(tree):
        return None
    return ga_dsl.tree_to_expression(tree)


def generate_brain_candidates(
    n: int,
    *,
    rng_seed: int = 1234,
    seed_exprs: Optional[list[str]] = None,
    fields: Optional[list[str]] = None,
    max_depth: int = 5,
) -> list[str]:
    """Produce n distinct, BRAIN-valid FASTEXPR expressions to simulate.

    Generation is template-first: most candidates are golden WorldQuant motifs
    (group_rank/neutralize over a normalized time-series signal) instantiated
    with REAL BRAIN fields (`fields`, from the data-fields API — fundamentals
    included), which is what actually clears the Sharpe/Fitness bars. The GA then
    mutates/crosses those for diversity. Seeds and generated trees feed the pool.
    Validation is grammar-free (BRAIN's field set is far larger than the local
    grammar) — structural only: BRAIN-safe ops, non-degenerate."""
    rng = random.Random(rng_seed)
    vocab = _build_vocab(fields)

    pool: list[dict] = []
    for expr in seed_exprs or ():
        try:  # best-effort: seeds using only locally-known ops/fields join the pool
            pool.append(expression_to_tree(expr))
        except Exception:  # noqa: BLE001 — a seed we can't parse just doesn't join
            continue

    seen: set[str] = set()
    out: list[str] = []
    guard = 0
    while len(out) < n and guard < n * 80:
        guard += 1
        r = rng.random()
        if r < 0.55:
            tree = _golden_template(rng, vocab)  # template-first
        elif pool and r < 0.85:
            a = rng.choice(pool)
            tree = (
                ga_dsl.mutate(rng, ga_dsl.crossover(rng, a, rng.choice(pool)), vocab)
                if len(pool) >= 2 and rng.random() < 0.5
                else ga_dsl.mutate(rng, a, vocab)
            )
        else:
            tree = ga_dsl.random_tree(rng, max_depth, vocab)

        if ga_dsl.tree_depth(tree) > max_depth:
            continue
        expr = _valid_brain_tree(tree)
        if expr is None or expr in seen:
            continue
        seen.add(expr)
        out.append(expr)
        pool.append(tree)  # feed back so the GA explores around good structures
    return out
