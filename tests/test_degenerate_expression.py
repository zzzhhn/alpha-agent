"""Regression: degenerate self-operation expressions (P0-1).

A black-box review fed the hypothesis "high earnings-yield long, low EY short"
into the Hypothesis Lab; the LLM translated it to

    sub(rank(div(net_income_adjusted, cap)), rank(div(net_income_adjusted, cap)))

which is sub(A, A) ≡ 0 — a zero-variance factor. The entire guard chain
(AST scorer, static validators, smoke probe, CTAs) let it through. This file
locks in the two new guards:

  1. validate_expression rejects sub(x, x) / div(x, x) when the two arms are
     structurally identical (ast.dump equality).
  2. smoke_test surfaces factor_std so the API can flag any other degenerate
     expression (e.g. multiply(0, x)) that isn't structurally self-cancelling.
"""
from __future__ import annotations

import pytest

from alpha_agent.core.factor_ast import (
    FactorSpecValidationError,
    validate_expression,
)
from alpha_agent.scan.smoke import smoke_test


# ── AST degenerate guard ───────────────────────────────────────────────────

def test_rejects_the_exact_review_bug():
    expr = (
        "sub(rank(div(net_income_adjusted, cap)), "
        "rank(div(net_income_adjusted, cap)))"
    )
    with pytest.raises(FactorSpecValidationError, match="degenerate"):
        validate_expression(expr, ["sub", "rank", "div"])


def test_rejects_simple_self_subtraction():
    with pytest.raises(FactorSpecValidationError, match="collapses to 0"):
        validate_expression("sub(close, close)", ["sub"])


def test_rejects_self_division():
    with pytest.raises(FactorSpecValidationError, match="constant 1"):
        validate_expression("div(rank(close), rank(close))", ["div", "rank"])


def test_rejects_subtract_alias():
    with pytest.raises(FactorSpecValidationError, match="degenerate"):
        validate_expression("subtract(returns, returns)", ["subtract"])


def test_allows_genuine_spread_different_fields():
    # Two arms differ in field → legitimate, must pass.
    used = validate_expression(
        "sub(rank(ts_mean(div(volume, close), 20)), rank(ts_zscore(returns, 20)))",
        ["sub", "rank", "ts_mean", "div", "ts_zscore"],
    )
    assert "sub" in used


def test_allows_spread_differing_only_in_lookback():
    # Same field + operator, different window → genuine momentum spread.
    used = validate_expression(
        "sub(ts_mean(returns, 5), ts_mean(returns, 20))",
        ["sub", "ts_mean"],
    )
    assert "sub" in used


# ── smoke factor_std degeneracy gauge ──────────────────────────────────────

def test_smoke_zero_variance_for_constant_factor():
    # multiply(0, x) passes the AST guard (not structurally self-cancelling)
    # but is degenerate — factor_std must be ~0 so the API flags it.
    r = smoke_test("multiply(0.0, rank(close))", 20)
    assert r.factor_std < 1e-9


def test_smoke_nonzero_variance_for_real_factor():
    r = smoke_test("rank(ts_mean(returns, 10))", 20)
    assert r.factor_std > 1e-6
