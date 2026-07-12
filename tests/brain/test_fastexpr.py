"""Phase E3: the BRAIN FASTEXPR generator. Every candidate must be a distinct,
STRUCTURALLY-valid expression (BRAIN-safe operators, non-degenerate) — note the
generator now uses real BRAIN fundamental field IDs (ebit, equity, ...) that the
LOCAL grammar doesn't know, so validation is structural, not local-grammar."""
import random
import re

from alpha_agent.brain import fastexpr as fe
from alpha_agent.core.factor_ast import expression_to_tree
from alpha_agent.evolution import ga_dsl


def _ops(expr: str) -> set[str]:
    # operator = identifier immediately followed by '(' (grammar-free)
    return set(re.findall(r"([a-z_][a-z0-9_]*)\s*\(", expr))


def _assert_brain_valid(expr: str) -> None:
    ops = _ops(expr)
    assert ops, f"no operators in {expr}"  # not a bare field
    assert all(op in fe.BRAIN_SAFE_OPS for op in ops), f"gated op in {expr}"


def test_generates_n_distinct_valid_candidates():
    cands = fe.generate_brain_candidates(20, rng_seed=1)
    assert len(cands) == 20
    assert len(set(cands)) == 20
    for e in cands:
        _assert_brain_valid(e)


def test_deterministic_under_seed():
    assert fe.generate_brain_candidates(15, rng_seed=7) == fe.generate_brain_candidates(
        15, rng_seed=7
    )


def test_seeded_generation_stays_valid():
    cands = fe.generate_brain_candidates(
        10,
        rng_seed=3,
        seed_exprs=["group_rank(ts_mean(returns, 20), subindustry)"],
    )
    assert len(cands) == 10
    for e in cands:
        _assert_brain_valid(e)


def test_generation_only_uses_brain_safe_operators():
    """No candidate may use a level-gated operator (e.g. ts_max) that BRAIN
    would reject with 'inaccessible or unknown operator'."""
    for expr in fe.generate_brain_candidates(30, rng_seed=9):
        ops = ga_dsl.used_operators(expression_to_tree(expr))
        assert ops  # non-empty (not a bare field)
        assert all(op in fe.BRAIN_SAFE_OPS for op in ops), f"gated op in {expr}"


def _ops_in(expr: str) -> set[str]:
    # operator = identifier immediately followed by '(' (grammar-free)
    return set(re.findall(r"([a-z_][a-z0-9_]*)\s*\(", expr))


def test_generation_uses_real_fundamental_fields():
    """With real BRAIN data-fields (which the local grammar doesn't know), the
    generator must still produce valid candidates that USE those fields —
    validation is structural, not local-grammar."""
    real = ["fnd6_operating_income", "fnd6_equity", "anl4_esteps"]
    cands = fe.generate_brain_candidates(25, rng_seed=2, fields=real)
    assert len(cands) == 25
    # Real fields enter only via the minority golden/GA paths, so whether any
    # single seed's 25 candidates include one is probabilistic (~60% per seed).
    # Aggregate a few seeds so the invariant — real fields DO reach the pool —
    # is checked without depending on one lucky RNG stream.
    joined = " ".join(
        e
        for s in range(2, 9)
        for e in fe.generate_brain_candidates(25, rng_seed=s, fields=real)
    )
    assert any(rf in joined for rf in real)
    # every candidate uses only BRAIN-safe operators
    for e in cands:
        ops = _ops_in(e)
        assert ops and all(op in fe.BRAIN_SAFE_OPS for op in ops)


def test_golden_structures_dominate():
    """Template-first generation: the group_rank/neutralize golden motifs should
    appear in the majority of candidates (not random price soup)."""
    cands = fe.generate_brain_candidates(40, rng_seed=5)
    golden = [c for c in cands if c.startswith(("group_rank", "group_neutralize", "group_zscore"))]
    assert len(golden) >= 12  # a healthy share are golden structures


def test_generation_is_family_and_axis_diverse():
    """Diversification: a batch must spread across peer groups, time-series
    transforms AND factor families — not collapse onto the single
    subindustry / ts_rank / value-blend mold that produced look-alike passers.
    These bounds fail on the old generator (all subindustry, only ts_rank/ts_mean,
    zero technical/style/extended-family signals)."""
    fields = ["ebit", "equity", "assets", "ebitda", "cashflow_op", "eps", "close",
              "bookvalue_ps", "debt", "debt_lt", "enterprise_value", "capex",
              "cash", "cash_st", "assets_curr"]
    cands = fe.generate_brain_candidates(40, rng_seed=7, fields=fields)
    assert len(cands) == 40 and len(set(cands)) == 40  # all distinct
    for c in cands:
        _assert_brain_valid(c)
    groups = {g for c in cands
              for g in re.findall(r"subindustry|industry|sector", c)}
    transforms = {t for c in cands
                  for t in re.findall(r"ts_(?:rank|zscore|mean|delta|std_dev)", c)}
    technical = sum(
        1 for c in cands
        if re.search(r"volume|ts_std_dev|ts_delta\(close|divide\(close, ts_mean", c)
    )
    style = sum(1 for c in cands if "fscore_" in c)
    ext_family = sum(
        1 for c in cands
        if re.search(r"enterprise_value|divide\((debt|debt_lt|cash|cash_st|capex|assets_curr)", c)
    )
    assert len(groups) >= 2, groups          # not all one peer grouping
    assert len(transforms) >= 4, transforms  # not just ts_rank/ts_mean
    assert technical >= 1                     # a price/volume family signal
    assert style >= 1                         # a pre-computed style-factor score
    assert ext_family >= 3                    # ratio families beyond profitability/value


def test_brain_settings_overrides():
    s = fe.brain_settings(decay=15)
    assert s["decay"] == 15
    assert s["language"] == "FASTEXPR"
    assert s["neutralization"] == "SUBINDUSTRY"


# --- G2: family signature + per-family cap ----------------------------------
from alpha_agent.brain.fastexpr import (  # noqa: E402
    _family_signature,
    _fld,
    _op,
    generate_brain_candidates,
)


def test_family_signature_collapses_denominator_swaps():
    # Same profitability bet, swapped denominator -> one family fingerprint.
    a = _op("divide", _fld("operating_income"), _fld("assets"))
    b = _op("divide", _fld("operating_income"), _fld("equity"))
    assert _family_signature(a) == _family_signature(b) == ("ratio", "profitability")


def test_family_signature_separates_distinct_families():
    prof = _op("divide", _fld("operating_income"), _fld("assets"))  # profitability
    lev = _op("divide", _fld("debt"), _fld("equity"))               # leverage
    assert _family_signature(prof) != _family_signature(lev)


def test_family_signature_unknown_field_not_over_collapsed():
    # An unknown fundamental keeps its exact name so two different signals stay
    # distinct (never fold together by accident).
    x = _op("rank", _fld("some_unknown_field"))
    y = _op("rank", _fld("other_unknown_field"))
    assert _family_signature(x) != _family_signature(y)


def test_family_cap_bounds_per_family_output():
    # With cap=2, no family fingerprint may appear more than twice in the output.
    from collections import Counter

    from alpha_agent.brain.fastexpr import _family_signature, expression_to_tree

    exprs = generate_brain_candidates(24, rng_seed=7, family_cap=2)
    counts: Counter = Counter()
    for e in exprs:
        try:
            counts[_family_signature(expression_to_tree(e))] += 1
        except Exception:
            pass
    assert exprs, "generator produced nothing"
    assert max(counts.values()) <= 2


def test_build_field_hints_pins_sign_and_flags_dead():
    """Field hints from history: a plain rank() at -0.99 pins the REVERSE
    direction; a reversed leg at +0.80 pins reverse too; a field tried twice
    that never beat |0.35| is dead; a strong single observation pins nothing
    below the 0.5 confidence bar."""
    from alpha_agent.brain.fastexpr import build_field_hints
    scored = [
        ("group_neutralize(rank(equity_value_score), sector)", -0.99),
        ("group_neutralize(reverse(rank(earnings_certainty_rank_derivative)), industry)", 0.80),
        ("group_neutralize(rank(asset_growth_rate), industry)", -0.02),
        ("group_neutralize(reverse(rank(asset_growth_rate)), sector)", 0.03),
        ("group_neutralize(rank(snt_value), industry)", 0.47),
    ]
    h = build_field_hints(scored)
    assert h["equity_value_score"]["sign"] == -1
    assert h["earnings_certainty_rank_derivative"]["sign"] == -1
    assert h["asset_growth_rate"]["dead"] is True
    assert h["asset_growth_rate"]["sign"] is None
    assert h["snt_value"]["sign"] is None and not h["snt_value"]["dead"]


def test_catalog_composite_blends_known_good_fields_with_pinned_signs():
    from alpha_agent.brain.fastexpr import (
        _SCORE_FIELDS, _catalog_composite_leg, _valid_brain_tree)
    hints = {
        "equity_value_score": {"n": 3, "best_abs": 0.99, "sign": -1, "dead": False},
        "financial_statement_value_score": {"n": 5, "best_abs": 0.83, "sign": -1, "dead": False},
        "multi_factor_acceleration_score_derivative": {"n": 6, "best_abs": 0.97, "sign": 1, "dead": False},
    }
    rng = random.Random(3)
    expr = _valid_brain_tree(_catalog_composite_leg(rng, _SCORE_FIELDS, hints))
    assert expr and "add(" in expr and "group_neutralize(" in expr
    # a pinned-negative field must appear reversed when present
    if "equity_value_score" in expr:
        assert "reverse(rank(equity_value_score" in expr
    # fewer than two eligible fields -> None (caller falls back to single leg)
    assert _catalog_composite_leg(
        rng, _SCORE_FIELDS,
        {"equity_value_score": {"n": 3, "best_abs": 0.99, "sign": -1, "dead": False}},
    ) is None


def test_score_focus_generation_skips_dead_fields():
    """A hint-steered score round must never spend a sim on a proven-dead field
    (the 2026-07-09 round burned ~9 of 12 sims re-testing dead fields and
    known-wrong signs)."""
    hints = {
        "equity_value_score": {"n": 3, "best_abs": 0.99, "sign": -1, "dead": False},
        "financial_statement_value_score": {"n": 5, "best_abs": 0.83, "sign": -1, "dead": False},
        "earnings_certainty_rank_derivative": {"n": 6, "best_abs": 0.84, "sign": -1, "dead": False},
        "asset_growth_rate": {"n": 5, "best_abs": 0.03, "sign": None, "dead": True},
        "consensus_analyst_rating": {"n": 4, "best_abs": 0.12, "sign": None, "dead": True},
        "distress_risk_measure": {"n": 3, "best_abs": 0.04, "sign": None, "dead": True},
    }
    exprs = generate_brain_candidates(
        10, family_focus="score", field_hints=hints, rng_seed=11)
    joined = " ".join(exprs)
    assert len(exprs) == 10
    for dead in ("asset_growth_rate", "consensus_analyst_rating", "distress_risk_measure"):
        assert dead not in joined, f"dead field {dead} was mined"
    assert any("add(" in e for e in exprs)  # composites present


_FRONTIER_EXPECTED_FAMILY = {
    "pv_corr": "microstructure", "pv_deep": "microstructure",
    "vol_shock": "microstructure", "rsv_corr": "microstructure",
    "resid_mom": "momentum", "seasonality": "seasonality",
    "overnight": "overnight", "iv_term": "iv_term", "iv_mom": "iv_term",
    "vrp": "vrp", "quality": "quality",
}


def test_frontier_motifs_valid_and_classified():
    """Every frontier motif must serialize to a BRAIN-valid expression AND
    classify into its intended economic family (the badge, saturation cap, and
    diversifier gate all key off family_of — a misclassification silently gives
    a new mechanism the wrong bar, e.g. iv-momentum swallowed by the saturated
    options family)."""
    from alpha_agent.brain.evolution import family_of
    for name, fn in fe._FRONTIER_MOTIFS:
        for seed in range(10):
            expr = fe._valid_brain_tree(fn(random.Random(seed)))
            assert expr is not None, f"motif {name} seed {seed} invalid"
            fam = family_of(expr)
            assert fam == _FRONTIER_EXPECTED_FAMILY[name], (
                f"motif {name} classified {fam}, expected "
                f"{_FRONTIER_EXPECTED_FAMILY[name]}: {expr[:80]}")


def test_frontier_round_covers_many_mechanisms():
    """A frontier round must spread its sims across mechanisms (niche quota),
    not re-roll one basin: >=5 distinct families in 12 candidates."""
    from alpha_agent.brain.evolution import family_of
    exprs = fe.generate_brain_candidates(12, family_focus="frontier", rng_seed=3)
    assert len(exprs) == 12
    fams = {family_of(e) for e in exprs}
    assert len(fams) >= 5, f"only {fams}"


def test_blend_expressions_stitches_with_safety_caps():
    """User-directed technique: stitch real passers with near-misses via add()
    (+optional weight/constant tilt). Contract: parents tracked (excluded from
    adjusted-corr), op-count/length submission caps enforced (community-reported
    ~64-op BRAIN limit; we hold 48), degenerate same-expression pairs skipped."""
    from alpha_agent.brain.fastexpr import (
        _MAX_EXPR_CHARS, _MAX_OPS_PER_EXPR, _OP_CALL_RE, blend_expressions)
    passed = [("group_rank(ts_rank(divide(ebit, cap), 252), subindustry)", "P1", 1.55)]
    near = [("group_neutralize(reverse(ts_corr(rank(close), rank(volume), 5)), subindustry)",
             "N1", 0.9)]
    out = blend_expressions(passed, near, random.Random(0), 6)
    assert out, "expected blends"
    for expr, parents in out:
        assert expr.startswith("add(")
        assert parents == frozenset({"P1", "N1"})
        assert len(_OP_CALL_RE.findall(expr)) <= _MAX_OPS_PER_EXPR
        assert len(expr) <= _MAX_EXPR_CHARS
    # no sources -> no blends (never fabricate)
    assert blend_expressions([], near, random.Random(0), 4) == []
    # an over-long parent cannot produce an over-long blend
    huge = [("rank(" + "ts_mean(close, 5), " * 200 + "close)", "P2", 2.0)]
    assert blend_expressions(huge, near, random.Random(0), 4) == []


def test_dispersion_family_valid_and_classified():
    """P3 analyst-dispersion family: every leg serializes to a BRAIN-valid
    expression, uses only API-dump-verified anl4 fields, and classifies as
    'dispersion' (NOT 'revision' — the high-low spread detector must precede the
    anl4->revision rule, else the second-moment signal inherits the wrong family
    cap and money sign)."""
    from alpha_agent.brain.evolution import family_of
    for seed in range(15):
        expr = fe._valid_brain_tree(fe._dispersion_leg(random.Random(seed)))
        assert expr is not None, f"dispersion seed {seed} invalid"
        assert family_of(expr) == "dispersion", f"{expr[:70]} -> {family_of(expr)}"
    exprs = fe.generate_brain_candidates(8, family_focus="dispersion", rng_seed=1)
    assert len(exprs) == 8
    assert all(family_of(e) == "dispersion" for e in exprs)
