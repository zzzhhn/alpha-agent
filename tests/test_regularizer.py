"""Tests for ASTRegularizer: complexity scoring, hashing, normalization."""

from __future__ import annotations

import pytest

from alpha_agent.factor_engine.ast_nodes import (
    BinaryOpNode,
    CallNode,
    ExprNode,
    FeatureNode,
    LiteralNode,
    UnaryOpNode,
)
from alpha_agent.factor_engine.regularizer import ASTRegularizer, ComplexityScore


@pytest.fixture()
def reg() -> ASTRegularizer:
    return ASTRegularizer()


def feature(name: str) -> FeatureNode:
    return FeatureNode(name=name)


def lit(v: float) -> LiteralNode:
    return LiteralNode(value=v)


def add(left: ExprNode, right: ExprNode) -> BinaryOpNode:
    return BinaryOpNode(op="+", left=left, right=right)


def mul(left: ExprNode, right: ExprNode) -> BinaryOpNode:
    return BinaryOpNode(op="*", left=left, right=right)


def sub(left: ExprNode, right: ExprNode) -> BinaryOpNode:
    return BinaryOpNode(op="-", left=left, right=right)


def call(name: str, *args: ExprNode) -> CallNode:
    return CallNode(func_name=name, args=args)


class TestComplexityScore:
    def test_single_literal(self, reg: ASTRegularizer) -> None:
        assert reg.complexity_score(lit(5.0)) == ComplexityScore(depth=1, node_count=1)

    def test_single_feature(self, reg: ASTRegularizer) -> None:
        assert reg.complexity_score(feature("close")) == ComplexityScore(depth=1, node_count=1)

    def test_unary_node(self, reg: ASTRegularizer) -> None:
        node = UnaryOpNode(op="-", operand=feature("close"))
        assert reg.complexity_score(node) == ComplexityScore(depth=2, node_count=2)

    def test_binary_node(self, reg: ASTRegularizer) -> None:
        assert reg.complexity_score(add(feature("close"), feature("open"))) == ComplexityScore(depth=2, node_count=3)

    def test_call_two_args(self, reg: ASTRegularizer) -> None:
        assert reg.complexity_score(call("Delta", feature("close"), lit(5.0))) == ComplexityScore(depth=2, node_count=3)

    def test_nested_depth(self, reg: ASTRegularizer) -> None:
        node = call("Rank", call("Delta", feature("close"), lit(5.0)))
        score = reg.complexity_score(node)
        assert score.depth == 3
        assert score.node_count == 4

    def test_unbalanced_tree(self, reg: ASTRegularizer) -> None:
        node = sub(add(feature("close"), feature("open")), feature("volume"))
        score = reg.complexity_score(node)
        assert score.depth == 3
        assert score.node_count == 5

    def test_depth_6_at_limit(self, reg: ASTRegularizer) -> None:
        node: ExprNode = feature("close")
        for _ in range(5):
            node = UnaryOpNode(op="-", operand=node)
        assert reg.complexity_score(node).depth == 6

    def test_depth_7_exceeds(self, reg: ASTRegularizer) -> None:
        node: ExprNode = feature("close")
        for _ in range(6):
            node = UnaryOpNode(op="-", operand=node)
        assert reg.complexity_score(node).depth == 7


class TestIsValidComplexity:
    def test_simple_valid(self, reg: ASTRegularizer) -> None:
        assert reg.is_valid_complexity(feature("close")) is True

    def test_depth_6_valid(self, reg: ASTRegularizer) -> None:
        node: ExprNode = feature("close")
        for _ in range(5):
            node = UnaryOpNode(op="-", operand=node)
        assert reg.is_valid_complexity(node) is True

    def test_depth_7_invalid(self, reg: ASTRegularizer) -> None:
        node: ExprNode = feature("close")
        for _ in range(6):
            node = UnaryOpNode(op="-", operand=node)
        assert reg.is_valid_complexity(node) is False

    def test_node_count_under_20_valid(self, reg: ASTRegularizer) -> None:
        # Balanced tree: depth 3, 7 nodes — well within limits
        left = add(feature("a"), feature("b"))
        right = add(feature("c"), feature("d"))
        node = add(left, right)
        score = reg.complexity_score(node)
        assert score.node_count == 7
        assert score.depth == 3
        assert reg.is_valid_complexity(node) is True

    def test_node_count_21_invalid(self, reg: ASTRegularizer) -> None:
        node: ExprNode = feature("f0")
        for i in range(1, 11):
            node = add(node, feature(f"f{i}"))
        assert reg.complexity_score(node).node_count == 21
        assert reg.is_valid_complexity(node) is False


class TestTreeHash:
    def test_same_tree_same_hash(self, reg: ASTRegularizer) -> None:
        a = add(feature("close"), feature("open"))
        b = add(feature("close"), feature("open"))
        assert reg.tree_hash(a) == reg.tree_hash(b)

    def test_different_trees(self, reg: ASTRegularizer) -> None:
        a = add(feature("close"), feature("open"))
        b = add(feature("close"), feature("volume"))
        assert reg.tree_hash(a) != reg.tree_hash(b)

    def test_commutative_add(self, reg: ASTRegularizer) -> None:
        assert reg.tree_hash(add(feature("close"), feature("open"))) == reg.tree_hash(add(feature("open"), feature("close")))

    def test_commutative_mul(self, reg: ASTRegularizer) -> None:
        assert reg.tree_hash(mul(feature("close"), lit(2.0))) == reg.tree_hash(mul(lit(2.0), feature("close")))

    def test_non_commutative_sub(self, reg: ASTRegularizer) -> None:
        assert reg.tree_hash(sub(feature("close"), feature("open"))) != reg.tree_hash(sub(feature("open"), feature("close")))

    def test_hash_is_sha256_hex(self, reg: ASTRegularizer) -> None:
        h = reg.tree_hash(feature("close"))
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_nested_commutative_same_structure(self, reg: ASTRegularizer) -> None:
        # Same tree structure, just inner children swapped: (a+b)+c vs (b+a)+c
        abc = add(add(feature("a"), feature("b")), feature("c"))
        bac = add(add(feature("b"), feature("a")), feature("c"))
        assert reg.tree_hash(reg.normalize(abc)) == reg.tree_hash(reg.normalize(bac))


class TestNormalize:
    def test_literal_unchanged(self, reg: ASTRegularizer) -> None:
        assert reg.normalize(lit(42.0)) == lit(42.0)

    def test_feature_unchanged(self, reg: ASTRegularizer) -> None:
        assert reg.normalize(feature("close")) == feature("close")

    def test_commutative_add_sorted(self, reg: ASTRegularizer) -> None:
        assert reg.normalize(add(feature("close"), feature("open"))) == reg.normalize(add(feature("open"), feature("close")))

    def test_mul_sorted(self, reg: ASTRegularizer) -> None:
        assert reg.normalize(mul(feature("close"), lit(2.0))) == reg.normalize(mul(lit(2.0), feature("close")))

    def test_sub_order_preserved(self, reg: ASTRegularizer) -> None:
        assert reg.normalize(sub(feature("close"), feature("open"))) != reg.normalize(sub(feature("open"), feature("close")))

    def test_nested_normalize_recurses(self, reg: ASTRegularizer) -> None:
        outer_ab = sub(add(feature("a"), feature("b")), feature("c"))
        outer_ba = sub(add(feature("b"), feature("a")), feature("c"))
        assert reg.normalize(outer_ab) == reg.normalize(outer_ba)

    def test_immutability(self, reg: ASTRegularizer) -> None:
        original = add(feature("close"), feature("open"))
        reg.normalize(original)
        assert original.left == feature("close")
        assert original.right == feature("open")
