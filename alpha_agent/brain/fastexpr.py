"""Phase E3: FASTEXPR alpha generator for the BRAIN miner.

Reuses the local GA's tree genetics (ga_dsl) with a BRAIN-specific Vocab — the
operators map 1:1 to FASTEXPR, only the field/group alphabet differs. On BRAIN
the fitness function IS the platform's simulate, so this is pure diverse
generation: seed with known-good alphas, mutate/crossover for local diversity,
gate on the grammar, dedupe. Phase E4's loop simulates these on BRAIN and keeps
the ones that clear the metric gates."""
from __future__ import annotations

import random
import re
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
# BRAIN per-expression complexity caps (submission-safety; the platform has
# rejected over-long/over-complex expressions — user recalls a ~64-operator
# rule; 48/1400 keeps margin under whatever the current limit is).
_MAX_OPS_PER_EXPR = 48
_MAX_EXPR_CHARS = 1400
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
    # Frontier motifs (P1). VERIFIED against the API /operators dump (GH run
    # 29000147527) — NOT the hand-curated wq_catalog json, which listed ts_min/
    # ts_max that BRAIN rejects ("unknown operator", 2026-07-11 sim_error).
    "ts_covariance", "last_diff_value",
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


# Analyst consensus-estimate fields CONFIRMED present in this account's mining
# history (the council's assumed anl4_eps_fy1_* names do NOT exist). Revision
# momentum = the CHANGE in these, which is the value-orthogonal anomaly.
_REVISION_FIELDS = (
    "anl4_afv4_eps_mean", "anl4_afv4_median_eps", "anl4_fcf_median",
    "anl4_cfo_mean", "anl4_capex_mean", "anl4_bvps_value",
)


def _revision_leg(rng: random.Random) -> dict:
    """Analyst estimate-REVISION momentum — the change in a consensus estimate,
    not its raw level (raw analyst levels average ~0.85 Sharpe and are value-
    contaminated; the revision is the real, value-orthogonal anomaly). Built only
    from CONFIRMED fields. Estimates are sparse on TOP3000, so base_settings_for
    pins anl4 signals to TOP1000. reverse(x) = -x tests both directions."""
    name = rng.choice(_REVISION_FIELDS)

    def bf() -> dict:
        return _op("ts_backfill", _fld(name), _lit(60))

    d = _lit(rng.choice((21, 63)))  # ~1 month / 1 quarter revision horizon
    group = _fld(rng.choice(("industry", "subindustry", "sector")))
    variant = rng.randint(0, 2)
    if variant == 0:
        # percent revision: change over d, scaled by |level| to normalize
        rev = _op("divide", _op("ts_delta", bf(), d),
                  _op("add", _op("abs", bf()), {"type": "literal", "value": 0.01}))
        leg = _op("rank", rev)
    elif variant == 1:
        rev = _op("ts_delta", _op("ts_mean", bf(), _lit(10)), d)  # smoothed revision
        leg = _op("rank", rev)
    else:
        rev = _op("ts_delta", _op("ts_delta", bf(), d), d)  # revision acceleration
        leg = _op("rank", rev)
    if rng.random() < 0.5:
        leg = _op("reverse", leg)
    return _op("group_neutralize", leg, group)


# NEW orthogonal families from the BRAIN catalog dump (real fields, cov>=0.9),
# built to break the value+options vocabulary ceiling. These are pre-built,
# individually-strong signals from the risk / factor-model / sentiment datasets.
_LOWVOL_FIELDS = (  # model51 Systematic Risk Metrics — the low-vol / BAB anomaly
    "beta_last_60_days_spy", "beta_last_90_days_spy", "beta_last_360_days_spy",
    "unsystematic_risk_last_90_days", "systematic_risk_last_90_days",
)
_SENTIMENT_FIELDS = (  # socialmedia12 + sentiment1 — news/social sentiment
    "scl12_sentiment", "snt_value", "snt_buzz_ret", "scl12_buzz",
    "snt1_d1_netrecpercent", "daily_equity_mood_indicator",
)
_MOMENTUM_FIELDS = (  # model77 — price & earnings momentum
    "fifty_to_two_hundred_day_price_ratio", "fifteen_to_thirtysix_week_price_ratio",
    "earnings_momentum_composite_score", "earnings_momentum_analyst_score",
)
_SCORE_FIELDS = (  # model77 + model16 — complete factor-model scores
    "financial_statement_value_score", "equity_value_score", "asset_growth_rate",
    "consensus_analyst_rating", "earnings_revision_magnitude", "distress_risk_measure",
    "growth_potential_rank_derivative", "earnings_certainty_rank_derivative",
    "multi_factor_acceleration_score_derivative",
)
_CATALOG_FAMILY_FIELDS = {
    "lowvol": _LOWVOL_FIELDS,
    "sentiment": _SENTIMENT_FIELDS,
    "momentum": _MOMENTUM_FIELDS,
    "score": _SCORE_FIELDS,
}
_ALL_CATALOG_FIELDS = (
    _LOWVOL_FIELDS + _SENTIMENT_FIELDS + _MOMENTUM_FIELDS + _SCORE_FIELDS
)


def build_field_hints(scored: list) -> dict:
    """Per-field steering hints from mining history (the miner's own DB rows).

    `scored` is [(expression, sharpe), ...]. For each catalog field, look at every
    scored expression that used it and take the observation with the largest
    |Sharpe|. Its direction pins the money sign: a plain rank() at -0.99 means the
    REVERSED leg is the money side (rank-based legs are antisymmetric), and a
    reversed leg at +0.80 means reversed too. Returns
      {field: {"n", "best_abs", "sign" (+1 plain / -1 reverse / None unknown),
               "dead" (tried >=2x, never past |0.35|)}}
    so generation stops re-flipping coins history has already called: 2026-07-09
    a 12-sim score round spent ~9 sims re-testing known-wrong signs and known-dead
    fields (rank(equity_value_score) at -0.99 TWICE when history showed the
    reverse at ~+0.99) and yielded zero passers."""
    hints: dict = {}
    for f in _ALL_CATALOG_FIELDS:
        best_abs, money, n = 0.0, None, 0
        for expr, sh in scored:
            if sh is None or f not in expr:
                continue
            n += 1
            plain_sign = -1 if f"reverse(rank({f}" in expr else 1
            direction = plain_sign if sh >= 0 else -plain_sign
            if abs(sh) > best_abs:
                best_abs, money = abs(sh), direction
        if n:
            hints[f] = {
                "n": n,
                "best_abs": best_abs,
                "sign": money if best_abs >= 0.5 else None,
                "dead": n >= 2 and best_abs < 0.35,
            }
    return hints


def _catalog_composite_leg(
    rng: random.Random, fields: tuple, hints: dict, *, banned: frozenset = frozenset()
) -> Optional[dict]:
    """Blend 2-3 KNOWN-GOOD catalog fields (history sign pinned, best |Sharpe|
    >= 0.55) into one rank-sum composite. The score family's best singles top out
    at ~0.8-1.0 individually — below the bar — but their sub-themes (anti-value /
    quality / acceleration) are internally diverse, so the blend can clear what no
    single field can, and dilutes correlation to any one existing alpha. None when
    fewer than two eligible fields (caller falls back to a single-field leg)."""
    good = []
    for f in fields:
        h = hints.get(f)
        if (f not in banned and h and not h["dead"] and h["sign"] is not None
                and h["best_abs"] >= 0.55):
            good.append(f)
    if len(good) < 2:
        return None
    k = 2 if len(good) == 2 or rng.random() < 0.5 else 3
    tree = None
    for f in rng.sample(good, k):
        leg = _op("rank", _fld(f))
        if hints[f]["sign"] < 0:
            leg = _op("reverse", leg)
        tree = leg if tree is None else _op("add", tree, leg)
    return _op("group_neutralize", tree,
               _fld(rng.choice(("industry", "subindustry", "sector"))))


# --- Frontier motifs (2026-07-11 research sweep: Alpha101/GTJA/qlib census + ---
# --- academic anomalies; see docs/superpowers/audits + memory brain_miner) ------
# Conventions extracted from the corpora: volume enters as volume/adv20 or
# rank(volume); price legs are rank()ed before ts_corr; corr windows 3-10,
# decay windows 4-16, outer ts_rank 15-32; depth sweet spot 3-5.

_IV_TENOR_PAIRS = (  # verified fields: term-structure slope = short - long tenor
    ("implied_volatility_call_60", "implied_volatility_call_270"),
    ("implied_volatility_call_120", "implied_volatility_call_1080"),
    ("implied_volatility_call_60", "implied_volatility_call_180"),
)
_IV_MOM_FIELDS = (
    "implied_volatility_call_60", "implied_volatility_call_120",
    "implied_volatility_mean_10", "implied_volatility_mean_120",
)


def _m_pv_corr(rng: random.Random) -> dict:
    """Price-volume divergence family — THE most recurring Alpha101 motif
    (58/83 use ts_corr; #3/#6/#13/#16/#44): fade windows where price rank and
    volume rank co-move."""
    p = rng.choice(("close", "open", "vwap", "high"))
    d = rng.choice((5, 8, 10))
    inner = _op("ts_corr", _op("rank", _fld(p)), _op("rank", _fld("volume")), _lit(d))
    leg = _op("reverse", inner)
    if rng.random() < 0.5:
        leg = _op("group_neutralize", leg, _fld(rng.choice(("industry", "subindustry"))))
    return leg


def _m_pv_deep(rng: random.Random) -> dict:
    """Deep composite (Alpha101 #71/GTJA workhorse):
    ts_rank(decay(corr(ts_rank(price), ts_rank(liquidity)))) — co-movement of
    time-series-normalized price and liquidity, then 'is that unusual?'."""
    p = rng.choice(("close", "low", "vwap"))
    return _op("ts_rank",
               _op("ts_decay_linear",
                   _op("ts_corr", _op("ts_rank", _fld(p), _lit(3)),
                       _op("ts_rank", _fld("adv20"), _lit(12)), _lit(18)),
                   _lit(4)),
               _lit(16))


def _m_vol_shock(rng: random.Random) -> dict:
    """Volume-surge x price-reversal (Alpha101 #43 / Gervais high-volume
    premium): high-volume selloffs bounce harder."""
    return _op("multiply",
               _op("ts_rank", _op("divide", _fld("volume"), _fld("adv20")), _lit(20)),
               _op("ts_rank", _op("reverse", _op("ts_delta", _fld("close"), _lit(7))),
                   _lit(8)))


def _m_rsv_corr(rng: random.Random) -> dict:
    """Stochastic-position x volume (Alpha101 #55 / qlib RSV): heavy volume at
    range extremes -> reversal."""
    # ts_rank(close, w) IS the stochastic position-in-range (BRAIN has no
    # ts_min/ts_max — API-verified; the (close-min)/(max-min) form sim_errors).
    w = rng.choice((12, 20))
    return _op("reverse",
               _op("ts_corr", _op("ts_rank", _fld("close"), _lit(w)),
                   _op("rank", _fld("volume")), _lit(6)))


def _m_resid_mom(rng: random.Random) -> dict:
    """Residual momentum approximation (Blitz/Huij/Martens; Robeco iMOM):
    12-1 month momentum, vol-scaled (the crash-killer detail), industry-
    neutralized (strips the sector bet ts_regression would need)."""
    sig = _op("divide",
              _op("subtract", _op("ts_sum", _fld("returns"), _lit(231)),
                  _op("ts_sum", _fld("returns"), _lit(21))),
              _op("ts_std_dev", _fld("returns"), _lit(231)))
    return _op("group_neutralize", _op("rank", sig),
               _fld(rng.choice(("industry", "subindustry"))))


def _m_seasonality(rng: random.Random) -> dict:
    """Cross-sectional seasonality (Heston-Sadka JFE 2008): same-calendar-month
    return repeats at annual lags; avg of the last 3 years' same-month return.
    Mechanically orthogonal to every level-based fundamental/option signal."""
    def mo(lag: int) -> dict:
        m = _op("divide", _op("ts_delta", _fld("close"), _lit(21)),
                _op("ts_delay", _fld("close"), _lit(21)))
        return _op("ts_delay", m, _lit(lag))
    avg = _op("add", _op("add", mo(231), mo(483)), mo(735))
    leg = _op("rank", avg)
    if rng.random() < 0.85:
        leg = _op("reverse", leg)  # 2026-07-11: plain scored -0.89 => contrarian wins
    return _op("group_neutralize", leg, _fld("industry"))


def _m_overnight(rng: random.Random) -> dict:
    """Overnight-vs-intraday tug-of-war (Lou/Polk/Skouras JFE 2019): the
    overnight component of returns persists; intraday reverses."""
    on = _op("subtract", _op("divide", _fld("open"),
                             _op("ts_delay", _fld("close"), _lit(1))), _lit(1))
    if rng.random() < 0.5:  # pure overnight persistence
        sig = _op("ts_mean", on, _lit(21))
    else:  # tug-of-war spread: overnight minus intraday
        intra = _op("subtract", _op("divide", _fld("close"), _fld("open")), _lit(1))
        sig = _op("subtract", _op("ts_mean", on, _lit(21)),
                  _op("ts_mean", intra, _lit(21)))
    return _op("group_neutralize", _op("rank", sig), _fld("industry"))


def _m_iv_term(rng: random.Random) -> dict:
    """IV term-structure slope (Vasquez JFQA 2017): tenor dimension of the
    surface — mechanically distinct from the saturated call-put SKEW (strike
    dimension). Slope innovations via ts_zscore."""
    short, long_ = rng.choice(_IV_TENOR_PAIRS)
    slope = _op("subtract", _fld(short), _fld(long_))
    # ts_decay_linear: the raw slope churned at 0.81 turnover (cap 0.35)
    leg = _op("ts_decay_linear", _op("rank", _op("ts_zscore", slope, _lit(60))),
              _lit(15))
    if rng.random() < 0.15:
        leg = _op("reverse", leg)  # 2026-07-11: reversed scored -1.24 => plain wins
    return _op("group_neutralize", leg, _fld(rng.choice(("sector", "subindustry"))))


def _m_iv_mom(rng: random.Random) -> dict:
    """IV momentum (community-documented alternative to skew level):
    decay-smoothed change in implied vol."""
    f = rng.choice(_IV_MOM_FIELDS)
    leg = _op("rank", _op("ts_decay_linear",
                          _op("ts_delta", _fld(f), _lit(25)), _lit(20)))
    if rng.random() < 0.15:
        leg = _op("reverse", leg)  # 2026-07-11: reversed scored -1.20 => plain wins
    return _op("group_neutralize", leg, _fld("subindustry"))


def _m_vrp(rng: random.Random) -> dict:
    """Stock-level variance risk premium (Bali & Hovakimian 2009), rank-space
    form (unit-free): short names whose realized vol runs hot vs implied."""
    w, iv = rng.choice(((120, "implied_volatility_mean_120"),
                        (21, "implied_volatility_mean_10")))
    spread = _op("subtract",
                 _op("rank", _op("ts_std_dev", _fld("returns"), _lit(w))),
                 _op("rank", _fld(iv)))
    leg = _op("reverse", spread) if rng.random() < 0.85 else spread
    return _op("group_neutralize", leg, _fld("subindustry"))


def _m_quality(rng: random.Random) -> dict:
    """Gross profitability GP/A (Novy-Marx 2013, 'the other side of value'):
    the quality ratio with the strongest large-cap evidence, NEGATIVELY
    correlated with value — hedges the saturated value book."""
    # gross_profit_to_assets_ratio: model77, coverage 1.0 — the exact Novy-Marx
    # TTM GP/A, pre-built (raw gross_profit is NOT a valid field; sim-errored).
    # gross_profit_margin_ttm_2 dropped: flat S=0.00/grade UNKN in two rounds.
    leg = _op("rank", _fld("gross_profit_to_assets_ratio"))
    return _op("group_rank" if rng.random() < 0.5 else "group_neutralize",
               leg, _fld(rng.choice(("industry", "subindustry"))))


def _m_frontier_composite(rng: random.Random) -> dict:
    """Cross-mechanism rank-sum composite — the DB-proven path over the bar:
    7 of our 14 REAL passers are add() two-leg composites (top one S=2.24),
    while single frontier legs plateau at ~0.9-1.1. Two near-uncorrelated ~0.9
    legs sum to ~1.25+ (rank scale is comparable across legs). Legs use the
    history-pinned money signs; pairs prefer cross-dataset combinations
    (option-surface x price legs share nothing mechanically)."""
    def leg_iv_mom() -> dict:  # +0.94/+0.93 twice (plain)
        f = rng.choice(_IV_MOM_FIELDS)
        return _op("rank", _op("ts_decay_linear",
                               _op("ts_delta", _fld(f), _lit(25)), _lit(20)))
    def leg_iv_slope() -> dict:  # +1.12 best (plain)
        short, long_ = rng.choice(_IV_TENOR_PAIRS)
        return _op("ts_decay_linear",
                   _op("rank", _op("ts_zscore",
                                   _op("subtract", _fld(short), _fld(long_)),
                                   _lit(60))), _lit(15))
    def leg_seasonality() -> dict:  # +0.95 twice (REVERSED = contrarian)
        def mo(lag: int) -> dict:
            m = _op("divide", _op("ts_delta", _fld("close"), _lit(21)),
                    _op("ts_delay", _fld("close"), _lit(21)))
            return _op("ts_delay", m, _lit(lag))
        return _op("reverse",
                   _op("rank", _op("add", _op("add", mo(231), mo(483)), mo(735))))
    def leg_overnight() -> dict:  # +0.87 best (plain)
        on = _op("subtract", _op("divide", _fld("open"),
                                 _op("ts_delay", _fld("close"), _lit(1))), _lit(1))
        return _op("rank", _op("ts_mean", on, _lit(21)))
    def leg_vol_shock() -> dict:  # +1.40 best (fails only Fitness solo)
        return _op("rank", _op("multiply",
                               _op("ts_rank", _op("divide", _fld("volume"),
                                                  _fld("adv20")), _lit(20)),
                               _op("ts_rank", _op("reverse",
                                                  _op("ts_delta", _fld("close"), _lit(7))),
                                   _lit(8))))
    pool = {
        "iv_mom": leg_iv_mom, "iv_slope": leg_iv_slope,
        "seasonality": leg_seasonality, "overnight": leg_overnight,
        "vol_shock": leg_vol_shock,
    }
    option_legs = {"iv_mom", "iv_slope"}
    a = rng.choice(sorted(pool))
    # prefer cross-dataset pairs: an option leg pairs with a price leg
    others = [k for k in sorted(pool) if k != a
              and not (k in option_legs and a in option_legs)]
    b = rng.choice(others)
    tree = _op("add", pool[a](), pool[b]())
    # Fitness lever (35%): signed_power(zscore(x), 2) amplifies conviction tails
    # keeping sign — composites clear Sharpe (1.56/1.32/1.18) but stall at
    # F≈0.8-0.9 because returns run at 0.07; tail emphasis lifts the return leg.
    if rng.random() < 0.35:
        tree = _op("signed_power", _op("zscore", tree), _lit(2))
    return _op("group_neutralize", tree,
               _fld(rng.choice(("industry", "subindustry"))))


_OP_CALL_RE = re.compile(r"[a-z_]+\(")


def blend_expressions(
    passed: list, near_misses: list, rng: random.Random, n: int
) -> list[tuple[str, frozenset]]:
    """Stitch REAL passers with near-miss candidates into new submissable
    factors (user-directed technique): add(P, N) or add(P, 0.5*N). The blend
    DILUTES correlation vs the ACTIVE book (official self-corr only sees
    submitted alphas — unsubmitted parents are invisible to the platform) while
    stacking performance. Parents are returned so the miner can EXCLUDE them
    from the adjusted-corr reference set (a blend always correlates with its
    own parents; that comparison is meaningless for a replacement candidate).

    `passed`/`near_misses`: [(expression, alpha_id, sharpe)]. Pairs prefer
    cross-family combinations. Submission-safety: op-count and length caps
    (community-reported ~64-op limit; margin held)."""
    from alpha_agent.brain.evolution import family_of
    out: list[tuple[str, frozenset]] = []
    seen: set[str] = set()
    if not passed or not near_misses:
        return out
    guard = 0
    while len(out) < n and guard < n * 30:
        guard += 1
        p_expr, p_id, _ = passed[rng.randrange(len(passed))]
        m_expr, m_id, _ = near_misses[rng.randrange(len(near_misses))]
        if p_expr == m_expr:
            continue
        # prefer cross-family pairs (same-family blends stay near the parent)
        if family_of(p_expr) == family_of(m_expr) and rng.random() < 0.7:
            continue
        w = rng.choice(("", "0.5", "0.75"))
        leg = m_expr if not w else f"multiply({m_expr}, {w})"
        expr = f"add({p_expr}, {leg})"
        if rng.random() < 0.25:  # small constant tilt variant
            expr = f"add({expr}, 0.1)"
        if expr in seen:
            continue
        if (len(expr) > _MAX_EXPR_CHARS
                or len(_OP_CALL_RE.findall(expr)) > _MAX_OPS_PER_EXPR):
            continue
        seen.add(expr)
        parents = frozenset(x for x in (p_id, m_id) if x)
        out.append((expr, parents))
    return out


# Registry: mechanism name -> generator. The frontier round cycles mechanisms
# (quota) so 12 sims always cover >=6 distinct mechanisms — the AutoAlpha/
# AlphaForge niche-quota idea at our scale.
_FRONTIER_MOTIFS: tuple = (
    ("pv_corr", _m_pv_corr),
    ("pv_deep", _m_pv_deep),
    ("vol_shock", _m_vol_shock),
    ("rsv_corr", _m_rsv_corr),
    ("resid_mom", _m_resid_mom),
    ("seasonality", _m_seasonality),
    ("overnight", _m_overnight),
    ("iv_term", _m_iv_term),
    ("iv_mom", _m_iv_mom),
    ("vrp", _m_vrp),
    ("quality", _m_quality),
)


# Analyst-forecast DISPERSION (P3, 2026-07-12). Diether/Malloy/Scherbina: high
# analyst disagreement predicts LOW future returns (short high dispersion). This
# is a SECOND-moment signal on anl4 estimates — orthogonal to our revision alpha
# (a first-moment level). All fields API-dump-verified (news12 VECTOR fields do
# NOT exist in our subscription, so the vec_avg/vec_sum route is dead; dispersion
# is the buildable P3 source). dispersion = (high - low) / |mean| = normalized
# forecast range. Metrics carry high/low/mean at the coverages noted.
_DISPERSION_METRICS = (
    ("anl4_afv4_eps_high", "anl4_afv4_eps_low", "anl4_afv4_eps_mean"),        # cov 1.0
    ("anl4_afv4_div_high", "anl4_afv4_div_low", "anl4_afv4_div_mean"),        # 0.82
    ("anl4_afv4_cfps_high", "anl4_afv4_cfps_low", "anl4_afv4_cfps_mean"),     # 0.68
    ("anl4_bvps_high", "anl4_bvps_low", "anl4_bvps_mean"),                    # 0.65
    ("anl4_ebitda_high", "anl4_ebitda_low", "anl4_ebitda_mean"),             # 0.58
)
_DISPERSION_STDDEV_FIELDS = ("adj_net_income_stddev",)  # direct stddev field


def _dispersion_leg(rng: random.Random) -> dict:
    """Analyst-forecast dispersion: rank(normalized high-low spread), REVERSED
    (Diether: short high dispersion -> long LOW dispersion is the money side; 85%
    exploit / 15% probe), group-neutralized. ~25% use the direct stddev field."""
    if rng.random() < 0.25:
        leg = _op("rank", _fld(rng.choice(_DISPERSION_STDDEV_FIELDS)))
    else:
        hi, lo, mean = rng.choice(_DISPERSION_METRICS)
        disp = _op("divide",
                   _op("subtract", _fld(hi), _fld(lo)),
                   _op("abs", _fld(mean)))
        leg = _op("rank", disp)
    if rng.random() < 0.85:
        leg = _op("reverse", leg)  # short high dispersion => long low dispersion
    return _op("group_neutralize", leg,
               _fld(rng.choice(("industry", "subindustry", "sector"))))


def _catalog_leg(
    rng: random.Random,
    fields: tuple,
    *,
    low_is_good: bool = False,
    hints: Optional[dict] = None,
    banned: frozenset = frozenset(),
) -> dict:
    """A pre-built factor score / risk metric ranked + group-neutralized — a complete
    signal from BRAIN's factor-model / risk / sentiment datasets (cov>=0.9, orthogonal
    to value/options). ~40% take the ts_delta (momentum of the score). reverse(x)=-x
    tests both signs (and long low-beta for the risk family)."""
    hints = hints or {}
    # History steering: never spend a sim on a field history has proven dead, and
    # respect the per-round repeat cap (banned) so one field can't eat the round.
    alive = [x for x in fields
             if x not in banned and not hints.get(x, {}).get("dead")]
    if not alive:
        # All good fields hit the per-round cap: over-cap a GOOD field (the sig
        # dedup still forces a different neutralization/wrap) rather than
        # resurrect a proven-dead one — a dead-field sim is a wasted slot.
        alive = [x for x in fields if not hints.get(x, {}).get("dead")]
    if not alive:  # the whole family is dead (e.g. lowvol): explore anyway
        alive = [x for x in fields if x not in banned] or list(fields)
    fname = rng.choice(alive)
    f = _fld(fname)
    # These fields are pre-built scores / risk metrics / levels — the LEVEL is the
    # signal. Differencing them (esp. the *_rank_derivative composites, already a
    # change) was pure noise: the random ts_delta diluted each family to a coin-flip
    # around Sharpe 0 while the plain rank surfaced real signal
    # (earnings_certainty_rank_derivative: reverse(rank)=+0.80 vs differenced=+0.25).
    # So rank the LEVEL + group-neutralize; reverse tests the opposite sign (and
    # longs low-beta/low-risk for the risk family).
    leg = _op("rank", f)
    sign = (hints.get(fname) or {}).get("sign")
    if low_is_good:
        want_reverse = True  # long low-beta / low-risk by construction
    elif sign is not None and rng.random() < 0.85:
        want_reverse = sign < 0  # exploit the historically-winning direction
    else:
        want_reverse = rng.random() < 0.5  # explore (unknown or the 15% probe)
    if want_reverse:
        leg = _op("reverse", leg)
    return _op("group_neutralize", leg, _fld(rng.choice(("industry", "subindustry", "sector"))))


def _options_leg(rng: random.Random) -> dict:
    """The user's PROVEN options-skew alpha (S=1.6-2.5 on TOP3000/TOP1000, verified
    from mining history): when the put-call OI ratio is LOW, take the CALL-minus-PUT
    implied-vol skew — RAW (ranking it, flipping the sign to put-call, dropping the
    PCR gate, and pinning to TOP500 each dropped Sharpe to ~0 / negative and were
    reverted) — gated by low PCR, group-neutralized, then wrapped in a liquidity
    trade_when (the passing variants all carry the outer volume gate; the ungated
    raw version is high-Sharpe but rejected on turnover). Variation only in tenor,
    PCR tenor, and neutralization group, so every candidate stays on the proven
    structure. Runs on the DEFAULT TOP3000 (see base_settings_for — no options pin)."""
    i = rng.randint(0, 1)  # implied-vol tenor 150 vs 180
    pcr = _fld(rng.choice(_OPTION_FIELDS["pcr_oi"]))
    skew = _op("subtract", _fld(_OPTION_FIELDS["iv_call"][i]),
               _fld(_OPTION_FIELDS["iv_put"][i]))  # CALL - PUT (proven sign)
    inner = _op("trade_when",
                _op("less", pcr, {"type": "literal", "value": 1.1}), skew, _lit(-1))
    neut = _op("group_neutralize", inner, _fld(rng.choice(("sector", "subindustry"))))
    vol_cond = rng.choice((
        _op("greater", _fld("volume"), _fld("adv20")),
        _op("greater", _fld("volume"),
            _op("divide", _op("ts_sum", _fld("volume"), _lit(5)), _lit(5))),
    ))
    return _op("trade_when", vol_cond, neut, _lit(-1))

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
    # Submission-safety: BRAIN rejects over-complex expressions (community-
    # reported per-expression operator cap ~64; we hold a safety margin).
    if len(ops) > _MAX_OPS_PER_EXPR:
        return None
    if any(op not in BRAIN_SAFE_OPS for op in ops):
        return None
    if _degenerate(tree):
        return None
    expr = ga_dsl.tree_to_expression(tree)
    if len(expr) > _MAX_EXPR_CHARS:
        return None
    return expr


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
    family_focus: Optional[str] = None,
    field_hints: Optional[dict] = None,
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
    # Frontier mechanism cycle: shuffled once, then round-robin, so a 12-candidate
    # round covers >=6 distinct mechanisms instead of re-rolling one basin.
    _frontier_order = list(_FRONTIER_MOTIFS)
    rng.shuffle(_frontier_order)
    _frontier_i = 0
    seen_sigs: set[tuple] = set()  # structural fingerprints for pool diversity
    family_counts: Counter = Counter()  # G2: cap near-duplicates per factor family
    out: list[str] = []
    guard = 0
    while len(out) < n and guard < n * 120:
        guard += 1
        r = rng.random()
        curated = False  # curated template trees skip the GA depth cap
        if family_focus == "composite":
            # All-composite round: the only structures clearing Sharpe 1.25;
            # this focus exists to grind their Fitness over 1.0.
            tree = _m_frontier_composite(rng)
            curated = True
        elif family_focus == "frontier":
            # 40% cross-mechanism composites (the DB-proven route over the bar);
            # 60% single-mechanism cycle (keeps per-mechanism info flowing).
            if rng.random() < 0.40:
                tree = _m_frontier_composite(rng)
            else:
                _name, _fn = _frontier_order[_frontier_i % len(_frontier_order)]
                _frontier_i += 1
                tree = _fn(rng)
            curated = True
        elif family_focus == "options":
            # Family-constrained round: mine ONLY the options-IV family (highest
            # Sharpe, orthogonal to value); base_settings_for runs it on TOP500.
            tree = _options_leg(rng)
        elif family_focus == "revision":
            # Family-constrained round: analyst estimate-revision momentum
            # (value-orthogonal); base_settings_for runs anl4 on TOP1000.
            tree = _revision_leg(rng)
        elif family_focus == "dispersion":
            # Analyst-forecast dispersion (Diether second-moment signal),
            # orthogonal to the revision first-moment alpha.
            tree = _dispersion_leg(rng)
            curated = True
        elif family_focus in _CATALOG_FAMILY_FIELDS:
            # Family-constrained catalog round, steered by mining history
            # (field_hints): dead fields skipped, winning sign pinned (85%
            # exploit / 15% probe), each field capped at 2 accepted uses per
            # round, and ~45% of candidates are 2-3 field COMPOSITES of the
            # known-good fields — individually ~0.8-Sharpe signals blended to
            # clear the bar a single field can't.
            fam_fields = _CATALOG_FAMILY_FIELDS[family_focus]
            used: Counter = Counter()
            for _e in out:
                for _cf in fam_fields:
                    if _cf in _e:
                        used[_cf] += 1
            banned = frozenset(_cf for _cf in fam_fields if used[_cf] >= 2)
            tree = None
            if rng.random() < 0.45:
                tree = _catalog_composite_leg(
                    rng, fam_fields, field_hints or {}, banned=banned)
            if tree is None:
                tree = _catalog_leg(
                    rng, fam_fields, low_is_good=(family_focus == "lowvol"),
                    hints=field_hints, banned=banned)
            curated = True
        elif r < 0.50:
            # Economic-ratio / style golden structures — the highest-signal path,
            # now DOMINANT (was 45%). Widening operators/fields diluted this and
            # tanked the pass rate, so the proven backbone leads again.
            tree = (
                _blended_ratio_template(rng, ratio_usage, prefer_industry)
                if rng.random() < 0.35
                else _ratio_template(rng, ratio_usage, prefer_industry)
            )
        elif r < 0.68:
            # Frontier motifs (research-validated structures: pv-corr, seasonality,
            # overnight, iv-term, vrp, quality...) get a fixed share of every
            # normal round so new mechanisms keep flowing into the book.
            _name, _fn = _frontier_order[_frontier_i % len(_frontier_order)]
            _frontier_i += 1
            tree = _fn(rng)
            curated = True
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

        if not curated and ga_dsl.tree_depth(tree) > max_depth:
            # GA/random trees respect the depth cap; curated research templates
            # (seasonality's 3-lag average, deep pv composites) are exempt — their
            # depth is by construction, not runaway growth.
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
