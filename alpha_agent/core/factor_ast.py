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

# T1 operands (in current factor_universe_1y.parquet — OHLCV + derived).
# T2 operands (sector / industry / cap / fundamentals) become accepted once
# factor_universe_sp100_v2.parquet is the active panel; until _load_panel
# switches over we still serve T1 to keep validation in sync with runtime data.
_ALLOWED_OPERANDS: frozenset[str] = frozenset({
    # T1 (always available)
    "close", "open", "high", "low", "volume", "returns", "vwap",
    # T2 metadata
    "cap", "sector", "industry", "subindustry", "exchange", "currency",
    # T2 derived dollar-volume windows (computed in run_factor_backtest)
    "adv5", "adv10", "adv20", "adv60", "adv120", "adv180", "dollar_volume",
    # T2 fundamentals — initial 8
    "revenue", "net_income_adjusted", "ebitda", "eps",
    "equity", "assets", "free_cash_flow", "gross_profit",
    # T2 fundamentals — 12 expanded (same yfinance pull, more rows)
    "current_assets", "current_liabilities",
    "long_term_debt", "short_term_debt",
    "cash_and_equivalents", "retained_earnings", "goodwill",
    "operating_income", "cost_of_goods_sold", "ebit",
    "operating_cash_flow", "investing_cash_flow",
})


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


# ── B3 (v3): tree extraction for the AST visualization drawer ──────────────


def expression_to_tree(expression: str) -> dict:
    """Parse a validated factor expression into a JSON-serializable tree.

    Node shapes:
      operator: {"type": "operator", "name": str, "args": [child, ...]}
      operand:  {"type": "operand",  "name": str}
      literal:  {"type": "literal",  "value": int | float}

    Pre-condition: caller has already passed `validate_expression`. This
    helper trusts the input and only converts the AST shape; it raises
    FactorSpecValidationError if it encounters anything `validate_expression`
    would have rejected, which means a bug not bad data.
    """
    try:
        tree = ast.parse(expression, mode="eval").body
    except SyntaxError as exc:
        raise FactorSpecValidationError(f"unparseable expression: {exc}") from exc
    return _node_to_dict(tree)


def _node_to_dict(node: ast.AST) -> dict:
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise FactorSpecValidationError(
                "only direct function calls allowed (no attribute/subscript call targets)"
            )
        return {
            "type": "operator",
            "name": node.func.id,
            "args": [_node_to_dict(a) for a in node.args],
        }
    if isinstance(node, ast.Name):
        return {"type": "operand", "name": node.id}
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return {"type": "literal", "value": node.value}
        raise FactorSpecValidationError(
            f"only numeric literals allowed (got {type(node.value).__name__})"
        )
    raise FactorSpecValidationError(
        f"disallowed AST node: {type(node).__name__}"
    )
