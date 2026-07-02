"""Phase C: the GA's expression-tree genetics. The invariant under test is that
random generation, mutation, and crossover NEVER violate the DSL grammar —
arities and argument kinds (expr / window / param / group) are always respected,
so every offspring serializes to a parseable expression the validators accept.
Also asserts the genetic operators are immutable (never touch their inputs)."""
import copy
import random

import pytest

from alpha_agent.core.factor_ast import expression_to_tree, validate_expression
from alpha_agent.evolution import ga_dsl as g


def _wellformed(tree: dict) -> None:
    """Assert a tree respects every op's arity and per-arg kind."""
    t = tree["type"]
    if t == "operand":
        assert tree["name"] in g.NUMERIC_FIELDS or tree["name"] in g.GROUP_FIELDS
        return
    if t == "literal":
        assert isinstance(tree["value"], (int, float))
        return
    assert t == "operator"
    sig = g.GA_OPS[tree["name"]]  # KeyError => op not in the curated set
    assert len(tree["args"]) == len(sig)
    for arg, kind in zip(tree["args"], sig):
        if kind == g.EXPR:
            assert arg["type"] in ("operator", "operand")
            if arg["type"] == "operand":
                assert arg["name"] in g.NUMERIC_FIELDS
            _wellformed(arg)
        elif kind == g.WINDOW:
            assert arg["type"] == "literal" and arg["value"] in g.WINDOWS
        elif kind == g.PARAM:
            assert arg["type"] == "literal" and arg["value"] in g.PARAMS
        elif kind == g.GROUP:
            assert arg["type"] == "operand" and arg["name"] in g.GROUP_FIELDS


# ── serialization roundtrip against the real grammar ──────────────────────
@pytest.mark.parametrize(
    "expr",
    [
        "rank(ts_mean(returns, 20))",
        "group_rank(returns, sector)",
        "divide(ts_std_dev(returns, 20), ts_mean(volume, 10))",
        "ts_corr(close, volume, 20)",
        "winsorize(zscore(returns), 3)",
    ],
)
def test_tree_to_expression_roundtrips_and_validates(expr):
    tree = expression_to_tree(expr)
    back = g.tree_to_expression(tree)
    # The serialized form is accepted by the real validator...
    used = validate_expression(back, g.used_operators(tree))
    assert used == frozenset(g.used_operators(tree))
    # ...and re-parsing it yields the same tree (stable roundtrip).
    assert expression_to_tree(back) == tree


# ── random generation ─────────────────────────────────────────────────────
def test_random_trees_are_wellformed_and_parseable():
    rng = random.Random(7)
    for _ in range(300):
        tree = g.random_tree(rng, depth=4)
        _wellformed(tree)
        # Every serialized tree parses back to an identical structure.
        assert expression_to_tree(g.tree_to_expression(tree)) == tree


# ── expr_paths never addresses a non-expr slot ────────────────────────────
def test_expr_paths_only_hit_expr_slots():
    tree = expression_to_tree("group_rank(ts_mean(returns, 20), sector)")
    for p in g.expr_paths(tree):
        node = g.at(tree, p)
        # window literal (20) and group field (sector) must be unreachable
        assert not (node["type"] == "literal")
        assert not (node["type"] == "operand" and node["name"] in g.GROUP_FIELDS)


# ── mutation: valid + immutable ───────────────────────────────────────────
def test_mutate_preserves_wellformedness_and_is_immutable():
    rng = random.Random(11)
    for _ in range(300):
        tree = g.random_tree(rng, depth=4)
        frozen = copy.deepcopy(tree)
        child = g.mutate(rng, tree)
        _wellformed(child)
        assert expression_to_tree(g.tree_to_expression(child)) == child
        assert tree == frozen  # input untouched


# ── crossover: valid + immutable ──────────────────────────────────────────
def test_crossover_preserves_wellformedness_and_is_immutable():
    rng = random.Random(13)
    for _ in range(300):
        a = g.random_tree(rng, depth=4)
        b = g.random_tree(rng, depth=4)
        fa, fb = copy.deepcopy(a), copy.deepcopy(b)
        child = g.crossover(rng, a, b)
        _wellformed(child)
        assert a == fa and b == fb  # inputs untouched


def test_operator_swap_keeps_same_arg_signature():
    # subtract(a, b) may only become another (EXPR, EXPR) op, never e.g. ts_mean.
    rng = random.Random(5)
    tree = expression_to_tree("subtract(returns, close)")
    seen_ops = set()
    for _ in range(80):
        child = g._mutate_operator(rng, tree)
        if child and child["type"] == "operator":
            seen_ops.add(child["name"])
    assert seen_ops  # some swaps happened
    for op in seen_ops:
        assert g.GA_OPS[op] == (g.EXPR, g.EXPR)
