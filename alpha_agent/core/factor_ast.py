"""AST-based validator for FactorSpec.expression.

The expression is restricted Python function-call syntax: every call target must
be in AllowedOperator (see core/types.py), every leaf name must be an allowed
operand (close, open, high, low, volume, returns, vwap) or an operator, and
constants must be numeric. Attribute access, subscripts, imports, and lambdas
are all rejected.

This gate is how we enforce "LLM-generated guaranteed-parseable FactorSpec"
instead of "LLM-generated maybe-executable code" (REFACTOR_PLAN.md §3.1).
"""

from __future__ import annotations

import ast
from collections.abc import Iterable

from alpha_agent.core.types import AllowedOperator

_ALLOWED_OPS: frozenset[str] = frozenset(AllowedOperator.__args__)

_ALLOWED_OPERANDS: frozenset[str] = frozenset(
    {"close", "open", "high", "low", "volume", "returns", "vwap"}
)


class FactorSpecValidationError(ValueError):
    """Raised when a FactorSpec.expression fails AST validation."""


def validate_expression(
    expression: str, declared_ops: Iterable[str]
) -> frozenset[str]:
    """Parse the expression and enforce the grammar.

    Returns the frozenset of operators actually used. Raises
    FactorSpecValidationError on any grammar violation.

    declared_ops (FactorSpec.operators_used) must match the used set exactly,
    so the LLM cannot claim to use operators it did not, nor omit operators
    it did — both point at a drifting schema.
    """
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise FactorSpecValidationError(f"unparseable expression: {exc}") from exc

    used_ops: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Expression, ast.Load)):
            continue
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise FactorSpecValidationError(
                    "only direct function calls allowed (no attribute/subscript call targets)"
                )
            if node.func.id not in _ALLOWED_OPS:
                raise FactorSpecValidationError(
                    f"unknown operator {node.func.id!r}; allowed: {sorted(_ALLOWED_OPS)}"
                )
            used_ops.add(node.func.id)
            for kw in node.keywords:
                raise FactorSpecValidationError(
                    f"keyword arguments not allowed (found {kw.arg!r})"
                )
            continue
        if isinstance(node, ast.Name):
            if node.id in _ALLOWED_OPS or node.id in _ALLOWED_OPERANDS:
                continue
            raise FactorSpecValidationError(
                f"unknown operand {node.id!r}; allowed: {sorted(_ALLOWED_OPERANDS)}"
            )
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
                continue
            raise FactorSpecValidationError(
                f"only numeric literals allowed (got {type(node.value).__name__})"
            )
        raise FactorSpecValidationError(
            f"disallowed AST node: {type(node).__name__}"
        )

    declared = frozenset(declared_ops)
    used = frozenset(used_ops)
    if declared != used:
        missing_from_declared = used - declared
        extra_in_declared = declared - used
        parts: list[str] = []
        if missing_from_declared:
            parts.append(f"used but not declared: {sorted(missing_from_declared)}")
        if extra_in_declared:
            parts.append(f"declared but unused: {sorted(extra_in_declared)}")
        raise FactorSpecValidationError(
            "operators_used does not match expression (" + "; ".join(parts) + ")"
        )

    return used
