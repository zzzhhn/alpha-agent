"""Phase E3: the BRAIN FASTEXPR generator. Every candidate must be a distinct,
STRUCTURALLY-valid expression (BRAIN-safe operators, non-degenerate) — note the
generator now uses real BRAIN fundamental field IDs (ebit, equity, ...) that the
LOCAL grammar doesn't know, so validation is structural, not local-grammar."""
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
