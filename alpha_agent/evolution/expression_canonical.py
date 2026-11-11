"""Pure formatting keys for proposal deduplication and grouping."""
from __future__ import annotations

import ast
import re

from alpha_agent.core.factor_ast import expression_to_tree
from alpha_agent.evolution.ga_dsl import tree_to_expression


def canonical_expression(expr: str) -> str:
    """Normalize DSL formatting, falling back safely for unsupported syntax.

    The tree extractor assumes validated input and can silently drop keyword
    arguments. Exclude those calls and verify the tree round trip so legacy or
    malformed expressions cannot be merged with a different expression.
    """
    normalized = " ".join(expr.split())
    try:
        parsed = ast.parse(normalized, mode="eval")
        if not any(isinstance(node, ast.Call) and node.keywords for node in ast.walk(parsed)):
            tree = expression_to_tree(normalized)
            canonical = tree_to_expression(tree)
            if expression_to_tree(canonical) == tree:
                return canonical
    except (ValueError, SyntaxError, TypeError, KeyError, OverflowError, RecursionError):
        pass
    normalized = re.sub(r"\s*([(),])\s*", r"\1", normalized)
    return normalized.replace(",", ", ")
