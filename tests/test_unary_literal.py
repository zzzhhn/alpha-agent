"""Regression: negative numeric literals in factor expressions.

Python's `ast` parses `-1` as `UnaryOp(USub, Constant(1))` -- there is no
"negative constant" node. The two factor-expression gates on the
hypothesis-translation path (core.factor_ast.validate_expression and
scan.vectorized.evaluate) only whitelisted Call/Name/Constant, so any
LLM-translated expression carrying a negative number argument
(winsorize bounds, multiply(-1, x), add(x, -0.5), ...) was rejected with
"disallowed AST node: UnaryOp" / "unsupported AST node UnaryOp".

Fix: both gates + the AST-viz tree builder now accept
`UnaryOp(USub|UAdd, Constant)` and fold the sign into the literal value.
Unary +/- on a sub-expression (e.g. `-rank(x)`) is still rejected with a
message pointing at `multiply(-1, expr)`.
"""
from __future__ import annotations

import numpy as np
import pytest

from alpha_agent.core.factor_ast import (
    FactorSpecValidationError,
    expression_to_tree,
    validate_expression,
)
from alpha_agent.scan.vectorized import evaluate


# ── validate_expression ───────────────────────────────────────────────────

def test_validate_allows_negative_literal_arg():
    used = validate_expression("multiply(-1, rank(returns))", ["multiply", "rank"])
    assert used == frozenset({"multiply", "rank"})


def test_validate_allows_negative_literal_in_multi_arg():
    used = validate_expression("winsorize(returns, -3, 3)", ["winsorize"])
    assert used == frozenset({"winsorize"})


def test_validate_allows_unary_plus_literal():
    used = validate_expression("add(returns, +0.5)", ["add"])
    assert used == frozenset({"add"})


def test_validate_rejects_unary_on_subexpression():
    # -rank(x): unary minus on a Call, not a literal. Message must point
    # the LLM (and the user) at the multiply(-1, expr) form.
    with pytest.raises(FactorSpecValidationError, match="multiply"):
        validate_expression("-rank(returns)", ["rank"])


def test_validate_rejects_logical_not_unary():
    # `not returns` parses to UnaryOp(Not, ...). Only +/- is allowed.
    with pytest.raises(FactorSpecValidationError, match="only unary"):
        validate_expression("not returns", [])


# ── expression_to_tree (AST visualization drawer) ─────────────────────────

def test_expression_to_tree_folds_negative_literal():
    tree = expression_to_tree("multiply(-1, rank(returns))")
    assert tree["type"] == "operator"
    assert tree["name"] == "multiply"
    # First arg is the folded -1 literal -- NO new "unary" node type, so the
    # frontend AST drawer needs no change.
    assert tree["args"][0] == {"type": "literal", "value": -1}


def test_expression_to_tree_folds_unary_plus():
    tree = expression_to_tree("add(returns, +0.5)")
    assert tree["args"][1] == {"type": "literal", "value": 0.5}


# ── scan.vectorized.evaluate ──────────────────────────────────────────────

def test_evaluate_negative_literal_arg():
    data = {"returns": np.array([0.1, 0.2, 0.3])}
    result = evaluate("add(returns, -1)", data)
    np.testing.assert_allclose(result, [-0.9, -0.8, -0.7])


def test_evaluate_unary_plus_literal_arg():
    data = {"returns": np.array([0.1, 0.2, 0.3])}
    result = evaluate("add(returns, +1)", data)
    np.testing.assert_allclose(result, [1.1, 1.2, 1.3])
