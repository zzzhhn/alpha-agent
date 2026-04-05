"""AST node types for the factor expression language.

The expression language supports:
- Features: $close, $volume, etc.
- Function calls: Rank(X), Mean(X, 20), Corr(X, Y, 20)
- Infix operators: +, -, *, /, **
- Unary negation: -X
- Comparison: >, <, >=, <=
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


@dataclass(frozen=True)
class ExprNode:
    """Base class for all AST nodes."""


@dataclass(frozen=True)
class LiteralNode(ExprNode):
    """A numeric literal (e.g., 5, 0.03, -1.5)."""

    value: float


@dataclass(frozen=True)
class FeatureNode(ExprNode):
    """A market data feature reference (e.g., $close, $volume)."""

    name: str  # "close", "volume", etc. (without the $ prefix)


@dataclass(frozen=True)
class UnaryOpNode(ExprNode):
    """Unary operation (currently only negation)."""

    op: str  # "-"
    operand: ExprNode


@dataclass(frozen=True)
class BinaryOpNode(ExprNode):
    """Binary infix operation (e.g., $close + $open, $volume * 2)."""

    op: str  # "+", "-", "*", "/", "**", ">", "<", ">=", "<="
    left: ExprNode
    right: ExprNode


@dataclass(frozen=True)
class CallNode(ExprNode):
    """Function call (e.g., Rank(X), Mean(X, 20), Corr(X, Y, 20))."""

    func_name: str
    args: tuple[ExprNode, ...]
