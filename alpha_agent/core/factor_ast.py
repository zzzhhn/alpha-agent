"""AST-based validator for FactorSpec.expression.

The expression is restricted Python function-call syntax, grammar-enforced
against the single source of truth in `brain_registry`. This gate is how we
turn "LLM-generated maybe-executable code" into "LLM-generated guaranteed-
parseable FactorSpec" (REFACTOR_PLAN.md §3.1).

Allowed forms (post B+ relaxation, 2026-04-18):
  * Function calls to any name in OPERATOR_NAMES (e.g., `ts_mean(close, 20)`).
  * Positional AND keyword arguments (e.g., `winsorize(x, std=4)`).
  * Comparison ops: `<`, `<=`, `==`, `!=`, `>`, `>=` (ast.Compare).
  * Boolean ops: `and`, `or` (ast.BoolOp).
  * Unary ops: `not`, `-x`, `+x` (ast.UnaryOp).
  * Operand names from OPERAND_NAMES (e.g., `close`, `fn_ebitda`).
  * Numeric literals and string literals (for enum-style kwargs like
    `bucket(rank(x), range='0,0.5,1')`).

Disallowed:
  * Attribute access, subscripts, imports, lambdas, comprehensions.
  * Assignments, starred args, f-strings with formatting, walrus.
  * Binary arithmetic (`x + y`): use `add(x, y)` instead — canonical form.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable

from alpha_agent.core.brain_registry import OPERAND_NAMES, OPERATOR_NAMES


class FactorSpecValidationError(ValueError):
    """Raised when a FactorSpec.expression fails AST validation."""


# AST node types that carry no identity information of their own (they are
# pure structural holders whose contents are validated via their fields).
_STRUCTURAL_NODES: tuple[type[ast.AST], ...] = (
    ast.Expression,
    ast.Load,
    ast.keyword,  # kwarg wrapper; kw.value is visited via ast.walk
    # cmpop subclasses (used inside ast.Compare.ops)
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
    # boolop subclasses (used inside ast.BoolOp.op)
    ast.And, ast.Or,
    # unaryop subclasses (used inside ast.UnaryOp.op)
    ast.Not, ast.USub, ast.UAdd, ast.Invert,
)

# AST node types that represent allowed compound expressions. We walk their
# children via ast.walk; nothing in these nodes carries identity that needs
# separate whitelisting beyond what their operands provide.
_COMPOUND_NODES: tuple[type[ast.AST], ...] = (
    ast.Compare,
    ast.BoolOp,
    ast.UnaryOp,
)


def validate_expression(
    expression: str, declared_ops: Iterable[str]
) -> frozenset[str]:
    """Parse the expression and enforce the grammar.

    Returns the frozenset of operators actually used (function-call names).
    Raises FactorSpecValidationError on any grammar violation.

    `declared_ops` (FactorSpec.operators_used) must match the used set
    exactly — the LLM cannot claim operators it did not use, nor omit ones
    it did. Either direction signals schema drift.
    """
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise FactorSpecValidationError(f"unparseable expression: {exc}") from exc

    used_ops: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, _STRUCTURAL_NODES):
            continue
        if isinstance(node, _COMPOUND_NODES):
            continue
        if isinstance(node, ast.Call):
            _validate_call(node, used_ops)
            continue
        if isinstance(node, ast.Name):
            _validate_name(node)
            continue
        if isinstance(node, ast.Constant):
            _validate_constant(node)
            continue
        raise FactorSpecValidationError(
            f"disallowed AST node: {type(node).__name__}"
        )

    _enforce_declared_matches_used(declared_ops, used_ops)
    return frozenset(used_ops)


def _validate_call(node: ast.Call, used_ops: set[str]) -> None:
    if not isinstance(node.func, ast.Name):
        raise FactorSpecValidationError(
            "only direct function calls allowed (no attribute/subscript call targets)"
        )
    op_name = node.func.id
    if op_name not in OPERATOR_NAMES:
        raise FactorSpecValidationError(
            f"unknown operator {op_name!r}; "
            f"see brain_registry.OPERATOR_NAMES ({len(OPERATOR_NAMES)} total)"
        )
    used_ops.add(op_name)
    # Starred args (f(*x)) would bypass kwarg whitelisting; reject.
    for arg in node.args:
        if isinstance(arg, ast.Starred):
            raise FactorSpecValidationError(
                f"starred arguments not allowed in {op_name}(...)"
            )
    # Each kwarg must have a string name (no **kwargs expansion) and its
    # value is validated recursively by ast.walk.
    for kw in node.keywords:
        if kw.arg is None:
            raise FactorSpecValidationError(
                f"**kwargs expansion not allowed in {op_name}(...)"
            )


def _validate_name(node: ast.Name) -> None:
    name = node.id
    if name in OPERATOR_NAMES or name in OPERAND_NAMES:
        return
    # Diagnostic: don't dump the full 190-item whitelist into the error.
    raise FactorSpecValidationError(
        f"unknown operand {name!r}; "
        f"not in OPERAND_NAMES ({len(OPERAND_NAMES)} total) "
        f"or OPERATOR_NAMES ({len(OPERATOR_NAMES)} total)"
    )


def _validate_constant(node: ast.Constant) -> None:
    value = node.value
    # bool is a subclass of int; reject True/False literals (use 1/0 if needed).
    if isinstance(value, bool):
        raise FactorSpecValidationError(
            "boolean literals not allowed (use 1/0 or a comparison)"
        )
    if isinstance(value, (int, float)):
        return
    if isinstance(value, str):
        # String constants support enum-style kwargs like range='0,0.5,1',
        # driver='gaussian'. We accept any printable string; downstream ops
        # will raise if the value is not recognized.
        return
    raise FactorSpecValidationError(
        f"only numeric and string literals allowed (got {type(value).__name__})"
    )


def _enforce_declared_matches_used(
    declared_ops: Iterable[str], used_ops: set[str]
) -> None:
    declared = frozenset(declared_ops)
    used = frozenset(used_ops)
    if declared == used:
        return
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
