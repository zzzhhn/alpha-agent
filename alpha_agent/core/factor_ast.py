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

# Phase 3a: the whitelist is the static built-ins UNION any operator names
# registered in extended_operators (Phase 3 LLM-authored, sandboxed at runtime).
# BUILTIN_OPS stays a fixed frozenset; the dynamic union is held in _ALLOWED_OPS
# and refreshed via refresh_allowed_ops(pool_or_dsn) at server startup and after
# each Phase 3d Approve. Validation reads _ALLOWED_OPS off the module (no DB hit
# on hot path).
BUILTIN_OPS: frozenset[str] = frozenset(AllowedOperator.__args__)
_ALLOWED_OPS: frozenset[str] = BUILTIN_OPS


def get_allowed_ops() -> frozenset[str]:
    """Read the current whitelist (built-ins UNION registered extended ops)."""
    return _ALLOWED_OPS


async def refresh_allowed_ops(pool_or_dsn) -> None:
    """Rebuild _ALLOWED_OPS from BUILTIN_OPS UNION extended_operators.name.
    Call at server startup and after a Phase 3d Approve so newly-registered
    names become validate-able without a server restart. Accepts either an
    asyncpg pool OR a DSN string (tests pass DSN; runtime passes pool)."""
    import asyncpg
    global _ALLOWED_OPS
    if isinstance(pool_or_dsn, str):
        conn = await asyncpg.connect(pool_or_dsn)
        try:
            rows = await conn.fetch("SELECT name FROM extended_operators")
        finally:
            await conn.close()
    else:
        rows = await pool_or_dsn.fetch("SELECT name FROM extended_operators")
    extended = frozenset(r["name"] for r in rows)
    _ALLOWED_OPS = BUILTIN_OPS | extended

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
    # T1.5a (v4) Compustat additions — shares_outstanding (cshoq) lets users
    # express market cap dynamically as `multiply(close, shares_outstanding)`,
    # essential for B/M, E/P, S/P value factors. total_liabilities (ltq) lets
    # debt ratios be expressed without going through long_term + short_term
    # individually. Both ride the existing PIT as-of join — no new pull.
    "shares_outstanding", "total_liabilities",
    # Bundle C.3 (v4) — insider Form 4 alt-alpha. `insider_net_dollars` is
    # the per-day signed dollar net (sum of P/purchase minus S/sale at
    # transaction price × shares) from SEC EDGAR Form 4 filings, filtered
    # to discretionary trades only (Cohen-Malloy-Pomorski 2012). Many
    # ticker-days have zero insider activity → NaN-filled by kernel.
    # Intended composition: rank(ts_mean(insider_net_dollars, 60)).
    "insider_net_dollars", "insider_n_buys", "insider_n_sells",
})


class FactorSpecValidationError(ValueError):
    """Raised when a FactorSpec.expression fails AST validation."""


# Binary ops that collapse to a constant when both arguments are structurally
# identical: sub(x, x) ≡ 0, div(x, x) ≡ 1. Either way the factor carries zero
# cross-sectional information. The LLM commonly emits this when mimicking the
# sub(rank(...), rank(...)) spread idiom but filling both arms identically
# (observed: the Basu E/P example translated to sub(rank(div(ni,cap)),
# rank(div(ni,cap)))). Caught here so it can never reach smoke/Zoo/backtest.
_DEGENERATE_BINARY_OPS: frozenset[str] = frozenset({"sub", "subtract", "div", "divide"})


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
            # Degenerate self-operation guard. ast.dump gives a canonical
            # structural string; equal dumps => the two arms are the same
            # sub-expression => constant output.
            if (
                node.func.id in _DEGENERATE_BINARY_OPS
                and len(node.args) == 2
                and ast.dump(node.args[0]) == ast.dump(node.args[1])
            ):
                collapses_to = (
                    "0" if node.func.id in {"sub", "subtract"} else "the constant 1"
                )
                raise FactorSpecValidationError(
                    f"degenerate expression: {node.func.id}(x, x) collapses to "
                    f"{collapses_to}; the two arguments are structurally identical, "
                    "so the factor carries no cross-sectional signal. A spread or "
                    "ratio factor must differ in at least one of: field, lookback "
                    "window, operator, or coefficient."
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
        # Python parses `-1` / `+0.5` as UnaryOp(USub|UAdd, Constant) -- there
        # is no negative-literal node. Allow unary +/- *only* on a numeric
        # literal so expressions like winsorize(returns, -3, 3) or
        # multiply(-1, rank(x)) pass. Negating a whole sub-expression
        # (`-rank(x)`) is still rejected -- use multiply(-1, expr) instead.
        if isinstance(node, ast.UnaryOp):
            if not isinstance(node.op, (ast.USub, ast.UAdd)):
                raise FactorSpecValidationError(
                    f"only unary +/- allowed (got {type(node.op).__name__})"
                )
            operand = node.operand
            if not (
                isinstance(operand, ast.Constant)
                and isinstance(operand.value, (int, float))
                and not isinstance(operand.value, bool)
            ):
                raise FactorSpecValidationError(
                    "unary +/- is only allowed on a numeric literal "
                    "(e.g. -0.5); to negate a sub-expression use "
                    "multiply(-1, expr)"
                )
            continue
        if isinstance(node, (ast.USub, ast.UAdd)):
            # The op node itself, visited by ast.walk after its UnaryOp
            # parent has already been validated above.
            continue
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
    if isinstance(node, ast.UnaryOp):
        # validate_expression has already guaranteed op is USub/UAdd and the
        # operand is a numeric literal. Fold the sign into the literal value
        # so the frontend AST drawer needs no new node type.
        if not isinstance(node.op, (ast.USub, ast.UAdd)):
            raise FactorSpecValidationError(
                f"only unary +/- allowed (got {type(node.op).__name__})"
            )
        inner = _node_to_dict(node.operand)
        if inner["type"] != "literal":
            raise FactorSpecValidationError(
                "unary +/- is only allowed on a numeric literal"
            )
        sign = -1 if isinstance(node.op, ast.USub) else 1
        return {"type": "literal", "value": inner["value"] * sign}
    raise FactorSpecValidationError(
        f"disallowed AST node: {type(node).__name__}"
    )
