"""Phase E3: the BRAIN FASTEXPR generator. Every candidate must be a distinct,
grammar-valid expression drawn only from the BRAIN vocabulary, generation must
be deterministic, and seeds must be accepted."""
import re

from alpha_agent.brain import fastexpr as fe
from alpha_agent.core.factor_ast import expression_to_tree, validate_expression
from alpha_agent.evolution import ga_dsl


def _assert_brain_valid(expr: str) -> None:
    tree = expression_to_tree(expr)
    # passes the real grammar validator (also rejects degenerate x-x / x/x)
    validate_expression(expr, ga_dsl.used_operators(tree))

    def walk(n: dict) -> None:
        if n["type"] == "operand":
            assert (
                n["name"] in fe.BRAIN_VOCAB.fields
                or n["name"] in fe.BRAIN_VOCAB.groups
            )
        elif n["type"] == "operator":
            for a in n["args"]:
                walk(a)

    walk(tree)


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
    joined = " ".join(cands)
    # at least one fundamental field actually made it into the candidates
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


def test_brain_settings_overrides():
    s = fe.brain_settings(decay=15)
    assert s["decay"] == 15
    assert s["language"] == "FASTEXPR"
    assert s["neutralization"] == "SUBINDUSTRY"
