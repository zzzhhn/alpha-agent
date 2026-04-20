"""Coverage for the B+ whitelist layer: registry, AST validator, OPS, smoke.

These tests gate the boundary between "LLM output" and "numeric pipeline"
(REFACTOR_PLAN.md §3.1). If any of these break, the HypothesisTranslator
either stops catching bad LLM output or starts rejecting valid output.
"""

from __future__ import annotations

import pytest

from alpha_agent.core.brain_registry import (
    IMPLEMENTED_OPERATOR_NAMES,
    OPERAND_NAMES,
    OPERANDS,
    OPERATOR_NAMES,
    OPERATORS,
)
from alpha_agent.core.factor_ast import (
    FactorSpecValidationError,
    validate_expression,
)
from alpha_agent.core.types import FactorSpec
from alpha_agent.scan.smoke import smoke_test
from alpha_agent.scan.vectorized import OPS, evaluate


# ── Registry ────────────────────────────────────────────────────────────────


class TestRegistry:
    def test_counts_are_stable(self):
        assert len(OPERATORS) == 57
        assert len(OPERANDS) == 190

    def test_ops_sets_consistent(self):
        assert OPERATOR_NAMES == frozenset(OPERATORS)
        assert OPERAND_NAMES == frozenset(OPERANDS)
        assert IMPLEMENTED_OPERATOR_NAMES <= OPERATOR_NAMES

    def test_operand_categories_match_source(self):
        by_cat: dict[str, int] = {}
        for spec in OPERANDS.values():
            by_cat[spec.category] = by_cat.get(spec.category, 0) + 1
        assert by_cat == {
            "PriceVolume": 40, "Fundamental": 58, "Model": 35,
            "Analyst": 40, "Sentiment": 17,
        }

    def test_every_op_has_signature_and_description(self):
        for name, spec in OPERATORS.items():
            assert spec.signature.startswith(name + "("), name
            assert spec.description, name


# ── FactorSpec (Pydantic) ──────────────────────────────────────────────────


class TestFactorSpecValidation:
    def _valid_kwargs(self):
        return dict(
            name="demo",
            hypothesis="h",
            expression="ts_zscore(close, 20)",
            operators_used=["ts_zscore"],
            lookback=20,
            universe="SP500",
            justification="j",
        )

    def test_valid_spec_accepted(self):
        spec = FactorSpec(**self._valid_kwargs())
        assert spec.operators_used == ["ts_zscore"]

    def test_unknown_operator_rejected(self):
        kwargs = self._valid_kwargs()
        kwargs["operators_used"] = ["ts_zscore", "phantom_op"]
        with pytest.raises(ValueError, match="unknown operators"):
            FactorSpec(**kwargs)

    def test_lookback_bounds_enforced(self):
        kwargs = self._valid_kwargs()
        kwargs["lookback"] = 4  # below min of 5
        with pytest.raises(ValueError):
            FactorSpec(**kwargs)


# ── AST validator ──────────────────────────────────────────────────────────


class TestASTValidator:
    def test_simple_call(self):
        used = validate_expression("ts_zscore(close, 20)", ["ts_zscore"])
        assert used == frozenset({"ts_zscore"})

    def test_nested_calls(self):
        expr = "rank(subtract(ts_mean(close, 20), close))"
        used = validate_expression(expr, ["rank", "subtract", "ts_mean"])
        assert used == frozenset({"rank", "subtract", "ts_mean"})

    def test_kwargs_accepted(self):
        used = validate_expression("winsorize(close, std=4)", ["winsorize"])
        assert used == frozenset({"winsorize"})

    def test_comparison_accepted(self):
        expr = "if_else(close > ts_mean(close, 20), close, 0)"
        used = validate_expression(expr, ["if_else", "ts_mean"])
        assert used == frozenset({"if_else", "ts_mean"})

    def test_boolean_ops_accepted(self):
        expr = "if_else(close > 100 and volume > 0, close, 0)"
        used = validate_expression(expr, ["if_else"])
        assert used == frozenset({"if_else"})

    def test_unary_minus_accepted(self):
        used = validate_expression("rank(-close)", ["rank"])
        assert used == frozenset({"rank"})

    def test_string_literal_accepted(self):
        # bucket expects range='...' as enum kwarg
        used = validate_expression(
            "bucket(close, range='0,0.5,1')", ["bucket"]
        )
        assert used == frozenset({"bucket"})

    def test_binop_rejected(self):
        with pytest.raises(FactorSpecValidationError, match="disallowed AST node"):
            validate_expression("close + open", [])

    def test_bool_literal_rejected(self):
        with pytest.raises(FactorSpecValidationError, match="boolean literals"):
            validate_expression("if_else(True, close, 0)", ["if_else"])

    def test_unknown_operator_rejected(self):
        with pytest.raises(FactorSpecValidationError, match="unknown operator"):
            validate_expression("phantom_op(close)", ["phantom_op"])

    def test_unknown_operand_rejected(self):
        with pytest.raises(FactorSpecValidationError, match="unknown operand"):
            validate_expression("ts_mean(not_a_field, 20)", ["ts_mean"])

    def test_attribute_access_rejected(self):
        with pytest.raises(FactorSpecValidationError):
            validate_expression("np.mean(close)", [])

    def test_declared_vs_used_mismatch(self):
        with pytest.raises(FactorSpecValidationError, match="operators_used"):
            validate_expression(
                "rank(ts_mean(close, 5))", ["rank"]  # missing ts_mean
            )
        with pytest.raises(FactorSpecValidationError, match="operators_used"):
            validate_expression(
                "rank(close)", ["rank", "ts_mean"]  # ts_mean declared but unused
            )


# ── Vectorized OPS ─────────────────────────────────────────────────────────


class TestVectorizedOps:
    def test_ops_covers_registry_exactly(self):
        assert set(OPS) == OPERATOR_NAMES

    def test_implemented_ops_do_not_raise_on_basic_input(self):
        import numpy as np
        rng = np.random.default_rng(0)
        close = 100 + np.cumsum(rng.normal(0, 1, (30, 5)), axis=0)
        volume = rng.uniform(1e6, 1e7, (30, 5))
        expressions = [
            "ts_zscore(close, 10)",
            "rank(ts_delta(close, 3))",
            "winsorize(zscore(close), std=4)",
            "ts_corr(close, volume, 10)",
            "if_else(close > 100, close, 0)",
            "signed_power(reverse(close), 2)",
            "abs(ts_delta(close, 1))",
            "max(ts_mean(close, 5), ts_mean(close, 10))",
        ]
        for expr in expressions:
            result = evaluate(expr, {"close": close, "volume": volume})
            assert result.shape == close.shape, expr

    def test_unimplemented_ops_raise(self):
        import numpy as np
        close = np.ones((10, 3))
        with pytest.raises(NotImplementedError, match="no vectorized impl"):
            evaluate("group_rank(close, close)", {"close": close})


# ── Smoke test ─────────────────────────────────────────────────────────────


class TestSmoke:
    def test_smoke_runs_across_all_categories(self):
        cases = [
            ("ts_zscore(close, 10)", 10),                  # PriceVolume
            ("rank(divide(sales, assets))", 5),            # Fundamental
            ("zscore(est_capex)", 5),                      # Analyst
            ("ts_zscore(snt1_d1_buyrecpercent, 5)", 5),    # Sentiment
            ("ts_zscore(beta_last_30_days_spy, 5)", 5),    # Model
        ]
        for expr, lb in cases:
            r = smoke_test(expr, lb)
            assert r.rows_valid > 0, expr
            assert r.runtime_ms < 200.0, f"{expr}: {r.runtime_ms}ms"

    def test_smoke_deterministic_with_seed(self):
        r1 = smoke_test("ts_zscore(close, 10)", 10, seed=42)
        r2 = smoke_test("ts_zscore(close, 10)", 10, seed=42)
        assert r1.ic_spearman == r2.ic_spearman
