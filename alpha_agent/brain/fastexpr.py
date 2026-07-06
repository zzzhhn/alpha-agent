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
# fetched (fundamentals/analyst), they're mixed in on top of these. operating_income
# / cap / adv20 / liabilities are CONFIRMED valid (they appear in the user's ACTIVE
# GOOD..SPECTACULAR alphas) — cap/adv20 had wrongly been dropped as "guesses".
_BASE_FIELDS = (
    "close", "open", "high", "low", "volume", "returns", "vwap",
    "operating_income", "cap", "adv20", "liabilities",
)

# Options fields from the user's ACTIVE options-skew alphas (the SPECTACULAR/
# EXCELLENT ones). Used only by the options-skew template.
_OPTION_FIELDS = {
    "pcr_oi": ("pcr_oi_270", "pcr_oi_120"),
    "iv_call": ("implied_volatility_call_150", "implied_volatility_call_180"),
    "iv_put": ("implied_volatility_put_150", "implied_volatility_put_180"),
}

# Economically MEANINGFUL fundamental ratios (numerator, denominator), grouped by
# FACTOR FAMILY. Different families are the real decorrelators: profitability and
# value ratios co-move, but leverage, liquidity, investment and EV-multiple signals
# are largely orthogonal — mixing families is what lets the passed set actually
# diversify. Every field id is CONFIRMED present in fundamental6 for USA/TOP3000/
# delay=1 (data-fields discovery), so they simulate as real operands, not
# "unknown variable" errors. random field pairs don't beat the bar; these encode
# real financial signal.
_RATIO_FAMILIES: dict[str, tuple[tuple[str, str], ...]] = {
    "profitability": (
        ("operating_income", "cap"),  # THE proven anchor (ts_rank(op_inc/cap,252))
        ("operating_income", "assets"),
        ("operating_income", "equity"),
        ("ebit", "equity"),          # operating return on equity
        ("ebit", "assets"),          # operating return on assets
        ("ebitda", "assets"),        # EBITDA / assets
        ("ebitda", "equity"),        # EBITDA / equity
        ("cashflow_op", "equity"),   # operating cash-flow yield on equity
        ("cashflow_op", "assets"),   # cash-flow return on assets
        ("cashflow", "assets"),      # total cash-flow return on assets
    ),
    "value": (
        ("operating_income", "cap"),         # earnings yield on market cap (proven)
        ("ebit", "cap"),                     # EBIT yield on market cap
        ("ebitda", "cap"),                   # EBITDA yield on market cap
        ("cashflow_op", "cap"),              # cash-flow yield on market cap
        ("eps", "close"),                    # earnings yield
        ("bookvalue_ps", "close"),           # book-to-price
        ("ebit", "enterprise_value"),        # EV/EBIT yield (EV angle)
        ("ebitda", "enterprise_value"),      # EV/EBITDA yield
        ("cashflow_op", "enterprise_value"), # cash-flow to EV
    ),
    "leverage": (
        ("equity", "assets"),        # equity ratio (low leverage = safety)
        ("debt", "equity"),          # debt-to-equity
        ("debt", "assets"),          # debt-to-assets
        ("debt_lt", "assets"),       # long-term leverage
        ("cashflow_op", "debt"),     # cash-flow debt coverage
    ),
    "liquidity": (
        ("cash", "assets"),          # cash ratio
        ("cash_st", "assets"),       # cash + short-term investments / assets
        ("assets_curr", "assets"),   # current-asset intensity
    ),
    "investment": (
        ("capex", "assets"),         # capex intensity (investment factor)
    ),
    "payout": (
        ("cashflow_dividends", "equity"),  # dividend payout on equity
    ),
}

# Flat tuple over all families — kept for the evolution usage-weighting + regex,
# and for callers that iterate every ratio.
ECONOMIC_RATIOS: tuple[tuple[str, str], ...] = tuple(
    r for fam in _RATIO_FAMILIES.values() for r in fam
)

# Pre-computed WorldQuant style-factor SCORES (model16 "Fundamental Scores"). Each
# is a complete, individually-strong factor DESIGNED to be relatively decorrelated
# from the others (the classic value/growth/quality/profitability/momentum styles).
# This is the cleanest diversity source — far better than re-deriving co-moving
# ratios. Confirmed in model16 for USA/TOP3000/delay=1.
_STYLE_FIELDS: tuple[str, ...] = (
    "fscore_value", "fscore_growth", "fscore_quality",
    "fscore_profitability", "fscore_momentum",
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
    # Widened coverage (all confirmed available via the /operators discovery, all
    # fit the op(x, int)/op(x, group) grammar so the positional serializer is safe):
    # NaN-fill, demeaned/scaled series, days-since-extreme momentum, group-scale.
    "ts_backfill", "ts_av_diff", "ts_scale", "ts_arg_max", "ts_arg_min",
    "group_scale",
    # Batch A (arithmetic, plain positional per the BRAIN /operators definitions:
    # max(x,y..) min(x,y..) power(x,y) signed_power(x,y) reverse(x)).
    "max", "min", "power", "signed_power", "reverse",
    # Batch B subset — the ops the user's ACTIVE GOOD..SPECTACULAR alphas rely on:
    # trade_when(cond, alpha, exit) gates the alpha to only trade when liquid;
    # greater/less build the trigger conditions (function form of > / <).
    "trade_when", "greater", "less",
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


# Empirically-highest-Sharpe ratio family (315-row mining history): the VALUE
# ratios — earnings/cash-flow yields and book-to-price on cap/close/enterprise_value
# denominators — average mean-Sharpe ~1.2-1.4 (cap 1.41, bookvalue_ps 1.31, eps
# 1.17), vs the profitability ratios on assets/equity denominators at ~0.67-0.86.
# So we TILT selection toward value. This is a QUALITY tilt (toward proven high
# Sharpe), the opposite of the reverted G4 diversity rotation (toward weak, under-
# used families); it optimizes the same objective the in-sample gate scores.
_VALUE_RATIOS = frozenset(_RATIO_FAMILIES["value"])
_VALUE_TILT = 2.2


def _pick_ratio(rng: random.Random, usage: Optional[dict]) -> tuple[str, str]:
    """Choose an economic ratio: a QUALITY tilt toward the empirically-strongest
    value family, times an inverse-usage anti-homogenization factor.

    Diversity is enforced at ACCEPTANCE (the G1 basket-orthogonality gate), where
    it costs no Sharpe — NOT here. An earlier family-UCB rotation (G4) that tilted
    the OTHER way (toward weak under-used families) was reverted: over exhausted
    vocabulary it halved the round's median Sharpe (0.39 -> 0.19) and every
    candidate failed the in-sample gate."""
    usage = usage or {}
    weights = [
        (_VALUE_TILT if r in _VALUE_RATIOS else 1.0) / (1 + usage.get(r, 0))
        for r in ECONOMIC_RATIOS
    ]
    return rng.choices(ECONOMIC_RATIOS, weights=weights, k=1)[0]


# Outer cross-sectional normalizations (all BRAIN-safe). group_rank → [0,1],
# group_zscore/neutralize → demeaned. Rotating the normalization decorrelates
# single-leg value alphas that would otherwise share an identical book.
_GROUP_NORMS = ("group_rank", "group_zscore", "group_neutralize", "group_scale")
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
    # ts_rank dominant — it's the proven high-Sharpe transform; the rest are a
    # minority for variety (they mostly clear the bar less often).
    inner = rng.choices(
        (
            _op("ts_rank", ratio, w),
            _op("ts_zscore", ratio, w),
            _op("ts_mean", ratio, w),
            _op("ts_av_diff", ratio, w),                    # demeaned level
            _op("ts_scale", ratio, w),                      # scaled to [0,1] over W
            _op("ts_rank", _op("ts_backfill", ratio, w), w),  # NaN-filled then ranked
            ratio,
        ),
        weights=(0.42, 0.15, 0.15, 0.07, 0.07, 0.07, 0.07),
        k=1,
    )[0]
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
            _op("ts_arg_max", _fld("close"), w),   # days since the high
            _op("ts_arg_min", _fld("close"), w),   # days since the low
        ))
    elif family == "volatility":
        inner = _op("ts_std_dev", _fld("returns"), w)
    else:  # liquidity
        inner = rng.choice((
            _op("ts_mean", _fld("volume"), w),
            _op("divide", _fld("volume"), _op("ts_mean", _fld("volume"), w)),
        ))
    return _op(norm, inner, _fld(group))


def _style_leg(rng: random.Random, group: str, *, norm: str = "group_rank") -> dict:
    """A pre-computed WorldQuant style-factor score (value / growth / quality /
    profitability / momentum) — a complete, individually-strong signal that is
    largely decorrelated from the others. The cleanest diversity source: growth and
    momentum styles genuinely decorrelate from the value/quality book the ratio
    legs produce, without sacrificing signal strength."""
    fld = _fld(rng.choice(_STYLE_FIELDS))
    w = _lit(rng.choice(_FUND_WINDOWS))
    inner = rng.choice((
        _op("ts_rank", fld, w),
        _op("ts_zscore", fld, w),
        fld,  # the score is already cross-sectional; group-rank it directly
    ))
    return _op(norm, inner, _fld(group))


def _trade_when_wrap(rng: random.Random, alpha: dict) -> dict:
    """The DOMINANT pattern across the user's ACTIVE alphas: gate the signal to only
    trade when the stock is liquid/active — trade_when(volume-condition, alpha, -1)
    (exit=-1 = never force-exit). Better execution → higher Sharpe / lower turnover,
    a big pass-rate lever."""
    cond = rng.choice((
        _op("greater", _fld("volume"), _fld("adv20")),                  # volume > adv20
        _op("less", _op("ts_mean", _fld("volume"), _lit(20)), _fld("volume")),
        _op("greater", _fld("volume"),
            _op("divide", _op("ts_sum", _fld("volume"), _lit(5)), _lit(5))),
    ))
    return _op("trade_when", cond, alpha, _lit(-1))


def _options_leg(rng: random.Random) -> dict:
    """The user's SPECTACULAR/EXCELLENT options-skew alpha: when the put-call open-
    interest ratio is low, take the call-minus-put implied-vol skew (same tenor),
    gated by trade_when and sector-neutralized. A complete alpha, not a blend leg."""
    i = rng.randint(0, 1)
    pcr = _fld(rng.choice(_OPTION_FIELDS["pcr_oi"]))
    skew = _op("subtract",
               _fld(_OPTION_FIELDS["iv_call"][i]), _fld(_OPTION_FIELDS["iv_put"][i]))
    gated = _op("trade_when", _op("less", pcr, {"type": "literal", "value": 1.1}),
                skew, _lit(-1))
    return _op("group_neutralize", gated, _fld("sector"))


def _reshape(rng: random.Random, leg: dict) -> dict:
    """RARELY reshape the final signal with a batch-A arithmetic op — signed_power
    compresses tails, power emphasizes extremes. Kept to a few percent: these alter
    the weighting profile and mostly HURT Sharpe, so the proven un-reshaped signal
    must dominate. `reverse` is deliberately NOT used here — flipping a good factor's
    sign turns a +Sharpe into a -Sharpe and just gets it rejected."""
    r = rng.random()
    if r < 0.04:
        return _op("signed_power", leg, {"type": "literal", "value": 0.5})
    if r < 0.06:
        return _op("power", leg, _lit(2))
    return leg


def _ratio_template(
    rng: random.Random,
    usage: Optional[dict] = None,
    prefer_industry: bool = False,
) -> dict:
    """A single golden signal. A fundamental-ratio leg (the proven Sharpe anchor,
    now spanning 6 factor families) with a ROTATED transform / peer group / outer
    normalization; a minority are pre-computed style-factor scores or technical
    signals for genuine signal-family spread. An occasional batch-A reshape alters
    the weighting profile."""
    # The user's options IV-skew alpha (a complete signal) — empirically the
    # HIGHEST-Sharpe family in the mining history (implied_volatility_*_180 mean
    # ~2.23, vs ~0.7-1.4 for fundamentals), yet it was a 10% minority. Raised to
    # ~22% so the generator actually spends budget on its strongest known motif.
    if rng.random() < 0.22:
        return _options_leg(rng)
    group = _neutral_group(rng, prefer_industry)
    # group_rank dominant (the proven high-Sharpe normalization); the others minority.
    norm = rng.choices(_GROUP_NORMS, weights=(0.70, 0.10, 0.10, 0.10), k=1)[0]
    r = rng.random()
    if r < 0.72:
        leg = _value_leg(rng, usage, group, norm=norm)    # fundamental ratio (backbone)
    elif r < 0.88:
        leg = _style_leg(rng, group, norm=norm)           # pre-computed style factor
    else:
        leg = _technical_leg(rng, group, norm=norm)       # price/volume family
    return _reshape(rng, leg)


def _blended_ratio_template(
    rng: random.Random,
    usage: Optional[dict] = None,
    prefer_industry: bool = False,
) -> dict:
    """Blend two group-RANKED legs (the LOW_FITNESS fix) that are DELIBERATELY
    cross-family, so the sum decorrelates from a book of look-alike value blends:
    a fundamental-ratio anchor (keeps the Sharpe hit-rate) plus a second leg that
    is a style-factor score, a technical signal, or a different-family ratio. Both
    legs are group_rank for scale-consistent addition; peer group and window differ
    per leg for extra decorrelation."""
    g1 = _neutral_group(rng, prefer_industry)
    g2 = _neutral_group(rng, prefer_industry)
    leg_a = _value_leg(rng, usage, g1, norm="group_rank")
    r = rng.random()
    if r < 0.4:
        leg_b = _style_leg(rng, g2, norm="group_rank")          # + style factor
    elif r < 0.7:
        leg_b = _technical_leg(rng, g2, norm="group_rank")      # + technical
    else:
        leg_b = _value_leg(rng, usage, g2, norm="group_rank")   # + different ratio
    # Combine two group-RANKED legs. add = average both; max/min = take the
    # stronger/weaker signal per stock (batch-A max(x,y)/min(x,y)).
    combine = rng.choices(("add", "max", "min"), weights=(0.7, 0.15, 0.15), k=1)[0]
    return _op(combine, leg_a, leg_b)


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


# G2 family signature. The structural signature keeps the EXACT field leaf, so
# divide(op_income, assets) and divide(op_income, equity) — the same profitability
# bet with a swapped denominator — read as distinct and both burn a slow sim slot.
# The family signature collapses a known economic-ratio subtree to its FAMILY and
# each field leaf to a coarse category, so field-swapped clones share one
# fingerprint; a per-round cap then stops any single family from dominating the
# batch (the mechanism behind "keep mining and only get near-duplicates").
_RATIO_FAMILY: dict[tuple[str, str], str] = {}
for _fam, _pairs in _RATIO_FAMILIES.items():
    for _pair in _pairs:
        _RATIO_FAMILY.setdefault(_pair, _fam)  # first family listing a shared pair wins
_STYLE_SET = frozenset(_STYLE_FIELDS)
_OPTION_SET = frozenset(f for grp in _OPTION_FIELDS.values() for f in grp)
_BASE_SET = frozenset(_BASE_FIELDS)


def _field_category(name: str) -> str:
    """Coarse bucket for a field leaf. Unknown fundamentals keep their exact name
    so we never OVER-collapse (two genuinely different fundamental signals must
    stay distinct); only the well-known style/option/base groups fold together."""
    if name in _STYLE_SET:
        return "style"
    if name in _OPTION_SET:
        return "option"
    if name in _BASE_SET:
        return "base"
    return name


def _family_signature(tree: dict) -> tuple:
    """Like _structural_signature but collapses a known ratio to its family and
    field leaves to categories — the granularity at which near-duplicates cluster."""
    if tree["type"] == "operand":
        return ("fld", _field_category(tree["name"]))
    if tree["type"] == "literal":
        return ("l",)
    if tree["name"] == "divide" and len(tree["args"]) == 2:
        a, b = tree["args"]
        if a.get("type") == "operand" and b.get("type") == "operand":
            fam = _RATIO_FAMILY.get((a["name"], b["name"]))
            if fam is not None:
                return ("ratio", fam)
    return (tree["name"], *(_family_signature(x) for x in tree["args"]))


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
    family_cap: int = 0,
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

    from collections import Counter

    seen: set[str] = set()
    seen_sigs: set[tuple] = set()  # structural fingerprints for pool diversity
    family_counts: Counter = Counter()  # G2: cap near-duplicates per factor family
    out: list[str] = []
    guard = 0
    while len(out) < n and guard < n * 120:
        guard += 1
        r = rng.random()
        if r < 0.62:
            # Economic-ratio / style golden structures — the highest-signal path,
            # now DOMINANT (was 45%). Widening operators/fields diluted this and
            # tanked the pass rate, so the proven backbone leads again.
            tree = (
                _blended_ratio_template(rng, ratio_usage, prefer_industry)
                if rng.random() < 0.35
                else _ratio_template(rng, ratio_usage, prefer_industry)
            )
        elif r < 0.72:
            # generic golden over any fetched field — kept small: raw single-field
            # signals over alt-data (news/social/option) fields are mostly junk.
            tree = _golden_template(rng, vocab)
        elif pool and r < 0.90:
            a = rng.choice(pool)
            try:
                tree = (
                    ga_dsl.mutate(rng, ga_dsl.crossover(rng, a, rng.choice(pool)), vocab)
                    if len(pool) >= 2 and rng.random() < 0.5
                    else ga_dsl.mutate(rng, a, vocab)
                )
            except Exception:  # noqa: BLE001 — GA can't mutate a BRAIN-only operator
                # (ts_backfill/ts_av_diff/... aren't in ga_dsl's registry); the
                # templates still emit those directly, so just skip this GA attempt.
                continue
        else:
            tree = ga_dsl.random_tree(rng, max_depth, vocab)

        if ga_dsl.tree_depth(tree) > max_depth:
            continue
        # Dominant ACTIVE pattern: gate the signal by a liquidity condition
        # (trade_when(volume>adv20, alpha, -1)). Applied after the depth check so the
        # 2-level wrap doesn't blow the budget; skip if already a trade_when.
        if tree.get("name") != "trade_when" and rng.random() < 0.35:
            tree = _trade_when_wrap(rng, tree)
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
        # G2 family cap (OFF by default, family_cap=0). A family contributes at
        # most `family_cap` candidates per round. Reverted from default-on: capping
        # the proven high-Sharpe families at generation forces weak filler from
        # other families, which fails the in-sample gate. Diversity is enforced at
        # ACCEPTANCE (G1) instead, where it costs no Sharpe. Kept + tested so it can
        # be re-enabled once the vocabulary carries more than a couple strong
        # families. 0 disables it.
        fam_sig = _family_signature(tree)
        if family_cap > 0 and family_counts[fam_sig] >= family_cap:
            continue
        seen.add(expr)
        seen_sigs.add(sig)
        family_counts[fam_sig] += 1
        out.append(expr)
        pool.append(tree)  # feed back so the GA explores around good structures
    return out
