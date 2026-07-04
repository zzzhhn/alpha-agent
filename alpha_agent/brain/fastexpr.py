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

# Economically MEANINGFUL fundamental ratios (numerator, denominator), using the
# real fundamental6 field IDs from the WorldQuant field snapshot. These encode
# actual financial signal — profitability, cash-flow yield, valuation — which is
# what beats the bar; random field pairs don't. This is the repo's golden combo
# group_rank(ts_rank(operating_income/equity, 126), subindustry) made concrete
# (ebit≈operating income, equity=common equity). Denominator 'close'/'cap' gives
# valuation ratios (earnings yield); fundamental/fundamental gives quality.
ECONOMIC_RATIOS: tuple[tuple[str, str], ...] = (
    ("ebit", "equity"),          # operating return on equity
    ("ebit", "assets"),          # operating return on assets
    ("ebitda", "assets"),        # EBITDA / assets
    ("ebitda", "equity"),        # EBITDA / equity
    ("cashflow_op", "equity"),   # operating cash-flow yield on equity
    ("cashflow_op", "assets"),   # cash-flow return on assets
    ("eps", "close"),            # earnings yield (valuation)
    ("bookvalue_ps", "close"),   # book-to-price (value)
    ("equity", "assets"),        # equity ratio (low leverage)
    ("cashflow_op", "debt"),     # cash-flow debt coverage
)

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
# Longer windows for fundamental signals (the repo's golden combo uses 126).
_FUND_WINDOWS = (60, 126, 252)


def _pick_ratio(rng: random.Random, usage: Optional[dict]) -> tuple[str, str]:
    """Choose an economic ratio, biased toward UNDER-used ones (self-evolution
    anti-homogenization): weight each ratio by 1/(1+times_used_recently)."""
    if not usage:
        return rng.choice(ECONOMIC_RATIOS)
    weights = [1.0 / (1 + usage.get(r, 0)) for r in ECONOMIC_RATIOS]
    return rng.choices(ECONOMIC_RATIOS, weights=weights, k=1)[0]


# Outer cross-sectional normalizations (all BRAIN-safe). group_rank → [0,1],
# group_zscore/neutralize → demeaned. Rotating the normalization decorrelates
# single-leg value alphas that would otherwise share an identical book.
_GROUP_NORMS = ("group_rank", "group_zscore", "group_neutralize")
# Technical legs prefer longer windows so their turnover stays inside the gate.
_TECH_WINDOWS = (20, 40, 60, 120)


def _neutral_group(rng: random.Random, prefer_industry: bool) -> str:
    """Peer grouping for the cross-sectional neutralization. A DIFFERENT grouping
    means a DIFFERENT residual, so rotating across subindustry/industry/sector is
    one of the cheapest decorrelators — the batch of look-alikes was ALL
    subindustry. subindustry stays the default (highest pass rate); sector is the
    broadest. When self-correlation runs high, `prefer_industry` biases away from
    the crowded subindustry book."""
    if prefer_industry:
        return rng.choices(
            ("industry", "subindustry", "sector"), weights=(0.5, 0.3, 0.2), k=1
        )[0]
    return rng.choices(
        ("subindustry", "industry", "sector"), weights=(0.55, 0.3, 0.15), k=1
    )[0]


def _value_leg(
    rng: random.Random,
    usage: Optional[dict],
    group: str,
    *,
    norm: str = "group_rank",
) -> dict:
    """A group-normalized fundamental value/quality signal — the proven high-Sharpe
    anchor. Rotates the time-series transform (ts_rank / ts_zscore / ts_mean / raw
    ratio) and window so two value alphas rarely share an identical normalization."""
    num, den = _pick_ratio(rng, usage)
    ratio = _op("divide", _fld(num), _fld(den))
    w = _lit(rng.choice(_FUND_WINDOWS))
    inner = rng.choice((
        _op("ts_rank", ratio, w),
        _op("ts_zscore", ratio, w),
        _op("ts_mean", ratio, w),
        ratio,
    ))
    return _op(norm, inner, _fld(group))


def _technical_leg(
    rng: random.Random, group: str, *, norm: str = "group_rank"
) -> dict:
    """A group-normalized price/volume signal from a family ORTHOGONAL to the value
    ratios — momentum, volatility or liquidity. Blending one onto a value anchor
    (or using it alone) is what actually decorrelates the passed set from a book of
    co-moving value factors. Uses only always-valid base fields + BRAIN-safe ops."""
    w = _lit(rng.choice(_TECH_WINDOWS))
    family = rng.choice(("momentum", "momentum", "volatility", "liquidity"))
    if family == "momentum":
        inner = rng.choice((
            _op("ts_rank", _fld(rng.choice(("close", "returns", "vwap"))), w),
            _op("ts_delta", _fld("close"), w),
            _op("divide", _fld("close"), _op("ts_mean", _fld("close"), w)),
        ))
    elif family == "volatility":
        inner = _op("ts_std_dev", _fld("returns"), w)
    else:  # liquidity
        inner = rng.choice((
            _op("ts_mean", _fld("volume"), w),
            _op("divide", _fld("volume"), _op("ts_mean", _fld("volume"), w)),
        ))
    return _op(norm, inner, _fld(group))


def _ratio_template(
    rng: random.Random,
    usage: Optional[dict] = None,
    prefer_industry: bool = False,
) -> dict:
    """A single golden signal. Predominantly a fundamental value leg (the proven
    Sharpe anchor) with a ROTATED transform / peer group / outer normalization so
    two value alphas don't collapse to the same book; a minority are pure technical
    signals for signal-family spread."""
    group = _neutral_group(rng, prefer_industry)
    norm = rng.choices(_GROUP_NORMS, weights=(0.6, 0.2, 0.2), k=1)[0]
    if rng.random() < 0.8:
        return _value_leg(rng, usage, group, norm=norm)
    return _technical_leg(rng, group, norm=norm)


def _blended_ratio_template(
    rng: random.Random,
    usage: Optional[dict] = None,
    prefer_industry: bool = False,
) -> dict:
    """Blend two group-RANKED legs (the LOW_FITNESS fix) that are DELIBERATELY
    cross-family / cross-transform, so the sum decorrelates from a book of
    look-alike value blends: a fundamental value anchor (keeps the Sharpe hit-rate)
    plus a second leg that is either a technical signal (momentum/vol/liquidity) or
    a different value ratio with a different transform. Both legs are group_rank for
    scale-consistent addition; peer group and window differ per leg for extra
    decorrelation."""
    g1 = _neutral_group(rng, prefer_industry)
    g2 = _neutral_group(rng, prefer_industry)
    leg_a = _value_leg(rng, usage, g1, norm="group_rank")
    leg_b = (
        _technical_leg(rng, g2, norm="group_rank")
        if rng.random() < 0.5
        else _value_leg(rng, usage, g2, norm="group_rank")
    )
    return _op("add", leg_a, leg_b)


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


def _structural_signature(tree: dict) -> tuple:
    """A structure/field fingerprint that IGNORES window/param literal values, so
    two candidates differing only by a window (ts_rank(x, 60) vs ts_rank(x, 126))
    collapse to the same signature. Used to diversify the candidate pool (AlphaEval
    Diversity dimension): simulating 15 near-identical alphas wastes the slow sim
    budget — one representative per signature is enough per round."""
    if tree["type"] == "operand":
        return ("f", tree["name"])
    if tree["type"] == "literal":
        return ("l",)  # value elided on purpose
    return (tree["name"], *(_structural_signature(a) for a in tree["args"]))


def generate_brain_candidates(
    n: int,
    *,
    rng_seed: int = 1234,
    seed_exprs: Optional[list[str]] = None,
    fields: Optional[list[str]] = None,
    max_depth: int = 5,
    ratio_usage: Optional[dict] = None,
    prefer_industry: bool = False,
    avoid_signatures: Optional[frozenset] = None,
) -> list[str]:
    """Produce n distinct, BRAIN-valid FASTEXPR expressions to simulate.

    Generation is template-first: most candidates are golden WorldQuant motifs
    (group_rank/neutralize over a normalized time-series signal) instantiated
    with REAL BRAIN fields (`fields`, from the data-fields API — fundamentals
    included), which is what actually clears the Sharpe/Fitness bars. The GA then
    mutates/crosses those for diversity. Seeds and generated trees feed the pool.
    Validation is grammar-free (BRAIN's field set is far larger than the local
    grammar) — structural only: BRAIN-safe ops, non-degenerate.

    Self-evolution hints (Phase F3, from mining history): `ratio_usage` biases
    generation toward under-used economic ratios; `prefer_industry` rotates
    neutralization when self-correlation is running high; `avoid_signatures`
    string-fingerprints of already-mined alphas are skipped (cross-round dedup)."""
    from alpha_agent.brain.evolution import expr_signature

    rng = random.Random(rng_seed)
    vocab = _build_vocab(fields)
    avoid = avoid_signatures or frozenset()

    pool: list[dict] = []
    for expr in seed_exprs or ():
        try:  # best-effort: seeds using only locally-known ops/fields join the pool
            pool.append(expression_to_tree(expr))
        except Exception:  # noqa: BLE001 — a seed we can't parse just doesn't join
            continue

    seen: set[str] = set()
    seen_sigs: set[tuple] = set()  # structural fingerprints for pool diversity
    out: list[str] = []
    guard = 0
    while len(out) < n and guard < n * 120:
        guard += 1
        r = rng.random()
        if r < 0.45:
            # Economic-ratio golden structures first — the highest-signal path.
            tree = (
                _blended_ratio_template(rng, ratio_usage, prefer_industry)
                if rng.random() < 0.35
                else _ratio_template(rng, ratio_usage, prefer_industry)
            )
        elif r < 0.65:
            tree = _golden_template(rng, vocab)  # generic golden over any field
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
        # Cross-round self-evolution: skip a candidate whose string-signature was
        # already mined (avoids re-proposing near-duplicates of past alphas that
        # would just fail SELF_CORRELATION).
        if expr_signature(expr) in avoid:
            continue
        # Diversity gate: skip candidates whose structure+fields duplicate an
        # already-accepted one (differing only by window/param) — don't burn the
        # slow BRAIN sim budget on near-identical alphas.
        sig = _structural_signature(tree)
        if sig in seen_sigs:
            continue
        seen.add(expr)
        seen_sigs.add(sig)
        out.append(expr)
        pool.append(tree)  # feed back so the GA explores around good structures
    return out
