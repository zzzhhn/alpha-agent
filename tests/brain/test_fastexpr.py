"""Phase E3: the BRAIN FASTEXPR generator. Every candidate must be a distinct,
grammar-valid expression drawn only from the BRAIN vocabulary, generation must
be deterministic, and seeds must be accepted."""
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


def test_brain_settings_overrides():
    s = fe.brain_settings(decay=15)
    assert s["decay"] == 15
    assert s["language"] == "FASTEXPR"
    assert s["neutralization"] == "SUBINDUSTRY"
