"""AST regularizer: complexity scoring, canonical hashing, and normalization.

Normalization sorts children of commutative operators (+, *) by their
tree_hash to produce a canonical form for structural deduplication.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from alpha_agent.factor_engine.ast_nodes import (
    BinaryOpNode,
    CallNode,
    ExprNode,
    FeatureNode,
    LiteralNode,
    UnaryOpNode,
)

_COMMUTATIVE_OPS: frozenset[str] = frozenset({"+", "*"})
_MAX_DEPTH: int = 6
_MAX_NODES: int = 20


@dataclass(frozen=True)
class ComplexityScore:
    """Structural complexity of an AST."""

    depth: int
    node_count: int


class ASTRegularizer:
    """Analyzes and normalizes factor expression ASTs."""

    def complexity_score(self, node: ExprNode) -> ComplexityScore:
        """Return depth and node_count for *node*."""
        return self._score(node)

    def is_valid_complexity(self, node: ExprNode) -> bool:
        """Return True iff depth <= 6 and node_count <= 20."""
        score = self._score(node)
        return score.depth <= _MAX_DEPTH and score.node_count <= _MAX_NODES

    def tree_hash(self, node: ExprNode) -> str:
        """Deterministic structural hash.

        Commutative children (+, *) are sorted by their own hashes before
        serialization so that ``a + b`` and ``b + a`` produce the same hash.
        """
        canonical = self._canonical(node)
        return hashlib.sha256(canonical.encode()).hexdigest()

    def normalize(self, node: ExprNode) -> ExprNode:
        """Return a new AST with commutative children sorted canonically."""
        return self._normalize(node)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _score(self, node: ExprNode) -> ComplexityScore:
        match node:
            case LiteralNode() | FeatureNode():
                return ComplexityScore(depth=1, node_count=1)

            case UnaryOpNode(operand=child):
                child_score = self._score(child)
                return ComplexityScore(
                    depth=1 + child_score.depth,
                    node_count=1 + child_score.node_count,
                )

            case BinaryOpNode(left=left, right=right):
                ls = self._score(left)
                rs = self._score(right)
                return ComplexityScore(
                    depth=1 + max(ls.depth, rs.depth),
                    node_count=1 + ls.node_count + rs.node_count,
                )

            case CallNode(args=args):
                if not args:
                    return ComplexityScore(depth=1, node_count=1)
                child_scores = [self._score(a) for a in args]
                return ComplexityScore(
                    depth=1 + max(s.depth for s in child_scores),
                    node_count=1 + sum(s.node_count for s in child_scores),
                )

            case _:
                raise ValueError(f"Unknown node type: {type(node).__name__}")

    def _canonical(self, node: ExprNode) -> str:
        """Build a deterministic prefix-notation string for hashing."""
        match node:
            case LiteralNode(value=v):
                return f"Lit({v!r})"

            case FeatureNode(name=n):
                return f"Feat({n})"

            case UnaryOpNode(op=op, operand=child):
                return f"Unary({op},{self._canonical(child)})"

            case BinaryOpNode(op=op, left=left, right=right):
                if op in _COMMUTATIVE_OPS:
                    children = sorted(
                        [self._canonical(left), self._canonical(right)]
                    )
                    return f"Bin({op},{children[0]},{children[1]})"
                return f"Bin({op},{self._canonical(left)},{self._canonical(right)})"

            case CallNode(func_name=fname, args=args):
                arg_strs = ",".join(self._canonical(a) for a in args)
                return f"Call({fname},{arg_strs})"

            case _:
                raise ValueError(f"Unknown node type: {type(node).__name__}")

    def _normalize(self, node: ExprNode) -> ExprNode:
        """Post-order rewrite: normalize children first, then sort if commutative."""
        match node:
            case LiteralNode() | FeatureNode():
                return node

            case UnaryOpNode(op=op, operand=child):
                return UnaryOpNode(op=op, operand=self._normalize(child))

            case BinaryOpNode(op=op, left=left, right=right):
                norm_left = self._normalize(left)
                norm_right = self._normalize(right)
                if op in _COMMUTATIVE_OPS:
                    children = sorted(
                        [norm_left, norm_right],
                        key=self.tree_hash,
                    )
                    return BinaryOpNode(op=op, left=children[0], right=children[1])
                return BinaryOpNode(op=op, left=norm_left, right=norm_right)

            case CallNode(func_name=fname, args=args):
                norm_args = tuple(self._normalize(a) for a in args)
                return CallNode(func_name=fname, args=norm_args)

            case _:
                raise ValueError(f"Unknown node type: {type(node).__name__}")
