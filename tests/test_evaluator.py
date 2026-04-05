"""Tests for the factor expression evaluator."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from alpha_agent.factor_engine.ast_nodes import (
    BinaryOpNode,
    CallNode,
    ExprNode,
    FeatureNode,
    LiteralNode,
    UnaryOpNode,
)
from alpha_agent.factor_engine.evaluator import EvaluationError, ExprEvaluator, _ts_apply


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def evaluator() -> ExprEvaluator:
    return ExprEvaluator()


@pytest.fixture()
def sample_data() -> pd.DataFrame:
    """3 stocks x 30 dates, deterministic synthetic data."""
    rng = np.random.default_rng(42)
    dates = pd.bdate_range("2024-01-01", periods=30)
    stocks = ["AAPL", "GOOG", "MSFT"]

    rows = []
    for stock in stocks:
        base = rng.uniform(100, 200)
        for i, date in enumerate(dates):
            close = base + rng.normal(0, 2)
            rows.append({
                "date": date,
                "stock_code": stock,
                "open": close - rng.uniform(0, 1),
                "close": close,
                "high": close + rng.uniform(0, 2),
                "low": close - rng.uniform(0, 2),
                "volume": rng.uniform(1e6, 5e6),
                "amount": rng.uniform(1e8, 5e8),
            })
            base = close  # random walk

    df = pd.DataFrame(rows).set_index(["date", "stock_code"])
    return df


# ---------------------------------------------------------------------------
# Basic node evaluation
# ---------------------------------------------------------------------------

class TestLiteralAndFeature:
    def test_literal_broadcasts(self, evaluator: ExprEvaluator, sample_data: pd.DataFrame):
        result = evaluator.evaluate(LiteralNode(3.14), sample_data)
        assert result.columns.tolist() == ["factor"]
        assert (result["factor"] == 3.14).all()
        assert result.index.equals(sample_data.index)

    def test_feature_extracts_column(self, evaluator: ExprEvaluator, sample_data: pd.DataFrame):
        result = evaluator.evaluate(FeatureNode("close"), sample_data)
        pd.testing.assert_series_equal(
            result["factor"], sample_data["close"], check_names=False
        )

    def test_unknown_feature_raises(self, evaluator: ExprEvaluator, sample_data: pd.DataFrame):
        with pytest.raises(EvaluationError, match="Feature 'nonexistent' not found"):
            evaluator.evaluate(FeatureNode("nonexistent"), sample_data)


# ---------------------------------------------------------------------------
# Unary and binary operations
# ---------------------------------------------------------------------------

class TestOperations:
    def test_negation(self, evaluator: ExprEvaluator, sample_data: pd.DataFrame):
        node = UnaryOpNode("-", FeatureNode("close"))
        result = evaluator.evaluate(node, sample_data)
        pd.testing.assert_series_equal(
            result["factor"], -sample_data["close"], check_names=False
        )

    def test_add(self, evaluator: ExprEvaluator, sample_data: pd.DataFrame):
        node = BinaryOpNode("+", FeatureNode("close"), FeatureNode("open"))
        result = evaluator.evaluate(node, sample_data)
        expected = sample_data["close"] + sample_data["open"]
        pd.testing.assert_series_equal(result["factor"], expected, check_names=False)

    def test_subtract(self, evaluator: ExprEvaluator, sample_data: pd.DataFrame):
        node = BinaryOpNode("-", FeatureNode("close"), FeatureNode("open"))
        result = evaluator.evaluate(node, sample_data)
        expected = sample_data["close"] - sample_data["open"]
        pd.testing.assert_series_equal(result["factor"], expected, check_names=False)

    def test_multiply_by_scalar(self, evaluator: ExprEvaluator, sample_data: pd.DataFrame):
        node = BinaryOpNode("*", FeatureNode("volume"), LiteralNode(2.0))
        result = evaluator.evaluate(node, sample_data)
        expected = sample_data["volume"] * 2.0
        pd.testing.assert_series_equal(result["factor"], expected, check_names=False)

    def test_division(self, evaluator: ExprEvaluator, sample_data: pd.DataFrame):
        node = BinaryOpNode("/", FeatureNode("amount"), FeatureNode("volume"))
        result = evaluator.evaluate(node, sample_data)
        expected = sample_data["amount"] / sample_data["volume"]
        pd.testing.assert_series_equal(result["factor"], expected, check_names=False)

    def test_comparison_gt(self, evaluator: ExprEvaluator, sample_data: pd.DataFrame):
        node = BinaryOpNode(">", FeatureNode("close"), FeatureNode("open"))
        result = evaluator.evaluate(node, sample_data)
        expected = (sample_data["close"] > sample_data["open"]).astype(float)
        pd.testing.assert_series_equal(result["factor"], expected, check_names=False)

    def test_power(self, evaluator: ExprEvaluator, sample_data: pd.DataFrame):
        node = BinaryOpNode("**", FeatureNode("close"), LiteralNode(0.5))
        result = evaluator.evaluate(node, sample_data)
        expected = sample_data["close"] ** 0.5
        pd.testing.assert_series_equal(result["factor"], expected, check_names=False)


# ---------------------------------------------------------------------------
# Time-series operators (per-stock)
# ---------------------------------------------------------------------------

class TestTimeSeriesOps:
    def test_ref_shifts_per_stock(self, evaluator: ExprEvaluator, sample_data: pd.DataFrame):
        """Ref(close, 1) should equal previous day's close for each stock."""
        node = CallNode("Ref", (FeatureNode("close"), LiteralNode(1)))
        result = evaluator.evaluate(node, sample_data)

        expected = sample_data["close"].groupby(level="stock_code").shift(1)
        pd.testing.assert_series_equal(result["factor"], expected, check_names=False)

    def test_ref_no_cross_stock_leakage(self, evaluator: ExprEvaluator, sample_data: pd.DataFrame):
        """First date for each stock should be NaN after Ref(close, 1)."""
        node = CallNode("Ref", (FeatureNode("close"), LiteralNode(1)))
        result = evaluator.evaluate(node, sample_data)

        for stock in ["AAPL", "GOOG", "MSFT"]:
            stock_data = result.xs(stock, level="stock_code")
            assert pd.isna(stock_data["factor"].iloc[0]), (
                f"First date for {stock} should be NaN"
            )

    def test_mean_rolling(self, evaluator: ExprEvaluator, sample_data: pd.DataFrame):
        """Mean(close, 5) should equal 5-day rolling mean per stock."""
        node = CallNode("Mean", (FeatureNode("close"), LiteralNode(5)))
        result = evaluator.evaluate(node, sample_data)

        expected = _ts_apply(sample_data["close"], lambda g: g.rolling(5).mean())
        pd.testing.assert_series_equal(
            result["factor"], expected, check_names=False, atol=1e-10
        )

    def test_delta(self, evaluator: ExprEvaluator, sample_data: pd.DataFrame):
        """Delta(close, 3) = close - Ref(close, 3)."""
        node = CallNode("Delta", (FeatureNode("close"), LiteralNode(3)))
        result = evaluator.evaluate(node, sample_data)

        shifted = sample_data["close"].groupby(level="stock_code").shift(3)
        expected = sample_data["close"] - shifted
        pd.testing.assert_series_equal(result["factor"], expected, check_names=False)

    def test_std(self, evaluator: ExprEvaluator, sample_data: pd.DataFrame):
        node = CallNode("Std", (FeatureNode("close"), LiteralNode(5)))
        result = evaluator.evaluate(node, sample_data)
        expected = _ts_apply(sample_data["close"], lambda g: g.rolling(5).std())
        pd.testing.assert_series_equal(
            result["factor"], expected, check_names=False, atol=1e-10
        )

    def test_sum(self, evaluator: ExprEvaluator, sample_data: pd.DataFrame):
        node = CallNode("Sum", (FeatureNode("volume"), LiteralNode(5)))
        result = evaluator.evaluate(node, sample_data)
        expected = _ts_apply(sample_data["volume"], lambda g: g.rolling(5).sum())
        pd.testing.assert_series_equal(
            result["factor"], expected, check_names=False, atol=1e-10
        )

    def test_ema(self, evaluator: ExprEvaluator, sample_data: pd.DataFrame):
        node = CallNode("EMA", (FeatureNode("close"), LiteralNode(10)))
        result = evaluator.evaluate(node, sample_data)
        expected = _ts_apply(sample_data["close"], lambda g: g.ewm(span=10).mean())
        pd.testing.assert_series_equal(
            result["factor"], expected, check_names=False, atol=1e-10
        )

    def test_slope(self, evaluator: ExprEvaluator, sample_data: pd.DataFrame):
        """Slope on a perfectly linear series should return constant slope."""
        # Build a small linear dataset: 2 stocks, 10 dates
        dates = pd.bdate_range("2024-01-01", periods=10)
        stocks = ["A", "B"]
        rows = []
        for stock in stocks:
            for i, d in enumerate(dates):
                val = 100.0 + i * 2.0 if stock == "A" else 50.0 + i * 3.0
                rows.append({
                    "date": d, "stock_code": stock,
                    "open": val, "close": val, "high": val,
                    "low": val, "volume": 1e6, "amount": 1e8,
                })
        linear_data = pd.DataFrame(rows).set_index(["date", "stock_code"])

        node = CallNode("Slope", (FeatureNode("close"), LiteralNode(5)))
        result = evaluator.evaluate(node, linear_data)

        # After warm-up (first 4 NaN), slope should be constant
        for stock, expected_slope in [("A", 2.0), ("B", 3.0)]:
            stock_result = result.xs(stock, level="stock_code")["factor"]
            valid = stock_result.dropna()
            np.testing.assert_allclose(valid.values, expected_slope, atol=1e-10)


# ---------------------------------------------------------------------------
# Cross-sectional operators (per-date)
# ---------------------------------------------------------------------------

class TestCrossSectionalOps:
    def test_rank_across_stocks(self, evaluator: ExprEvaluator, sample_data: pd.DataFrame):
        """Rank should operate across stocks within each date."""
        node = CallNode("Rank", (FeatureNode("close"),))
        result = evaluator.evaluate(node, sample_data)

        expected = sample_data["close"].groupby(level="date").rank(pct=True)
        pd.testing.assert_series_equal(result["factor"], expected, check_names=False)

    def test_rank_values_between_0_and_1(self, evaluator: ExprEvaluator, sample_data: pd.DataFrame):
        node = CallNode("Rank", (FeatureNode("close"),))
        result = evaluator.evaluate(node, sample_data)
        assert (result["factor"] >= 0).all()
        assert (result["factor"] <= 1).all()

    def test_zscore_mean_zero(self, evaluator: ExprEvaluator, sample_data: pd.DataFrame):
        """Zscore should produce mean ~ 0 across stocks for each date."""
        node = CallNode("Zscore", (FeatureNode("close"),))
        result = evaluator.evaluate(node, sample_data)

        per_date_mean = result["factor"].groupby(level="date").mean()
        np.testing.assert_allclose(per_date_mean.values, 0.0, atol=1e-10)

    def test_rank_is_cross_sectional_not_time_series(
        self, evaluator: ExprEvaluator, sample_data: pd.DataFrame
    ):
        """Verify Rank groups by date (cross-sectional), not by stock."""
        node = CallNode("Rank", (FeatureNode("close"),))
        result = evaluator.evaluate(node, sample_data)

        # With 3 stocks, rank(pct=True) values should be in {1/3, 2/3, 1.0}
        unique_ranks = set(result["factor"].round(6).unique())
        expected_ranks = {round(i / 3, 6) for i in range(1, 4)}
        assert unique_ranks == expected_ranks


# ---------------------------------------------------------------------------
# Element-wise operators
# ---------------------------------------------------------------------------

class TestElementWiseOps:
    def test_abs(self, evaluator: ExprEvaluator, sample_data: pd.DataFrame):
        inner = BinaryOpNode("-", FeatureNode("close"), FeatureNode("open"))
        node = CallNode("Abs", (inner,))
        result = evaluator.evaluate(node, sample_data)
        expected = (sample_data["close"] - sample_data["open"]).abs()
        pd.testing.assert_series_equal(result["factor"], expected, check_names=False)

    def test_sign(self, evaluator: ExprEvaluator, sample_data: pd.DataFrame):
        inner = BinaryOpNode("-", FeatureNode("close"), FeatureNode("open"))
        node = CallNode("Sign", (inner,))
        result = evaluator.evaluate(node, sample_data)
        assert set(result["factor"].unique()).issubset({-1.0, 0.0, 1.0})

    def test_log(self, evaluator: ExprEvaluator, sample_data: pd.DataFrame):
        node = CallNode("Log", (FeatureNode("close"),))
        result = evaluator.evaluate(node, sample_data)
        expected = np.log(sample_data["close"])
        pd.testing.assert_series_equal(result["factor"], expected, check_names=False)


# ---------------------------------------------------------------------------
# Conditional
# ---------------------------------------------------------------------------

class TestConditional:
    def test_if(self, evaluator: ExprEvaluator, sample_data: pd.DataFrame):
        cond = BinaryOpNode(">", FeatureNode("close"), FeatureNode("open"))
        node = CallNode("If", (cond, LiteralNode(1.0), LiteralNode(-1.0)))
        result = evaluator.evaluate(node, sample_data)

        mask = sample_data["close"] > sample_data["open"]
        expected = pd.Series(
            np.where(mask, 1.0, -1.0), index=sample_data.index
        )
        pd.testing.assert_series_equal(result["factor"], expected, check_names=False)


# ---------------------------------------------------------------------------
# Nested expressions
# ---------------------------------------------------------------------------

class TestNested:
    def test_rank_of_delta(self, evaluator: ExprEvaluator, sample_data: pd.DataFrame):
        """Rank(Delta($close, 5)) - a common alpha factor pattern."""
        delta_node = CallNode("Delta", (FeatureNode("close"), LiteralNode(5)))
        rank_node = CallNode("Rank", (delta_node,))
        result = evaluator.evaluate(rank_node, sample_data)

        # Should still be valid rank values in [0, 1] (NaN where Delta is NaN)
        valid = result["factor"].dropna()
        assert (valid >= 0).all()
        assert (valid <= 1).all()


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

class TestErrors:
    def test_unknown_function(self, evaluator: ExprEvaluator, sample_data: pd.DataFrame):
        node = CallNode("FooBar", (FeatureNode("close"),))
        with pytest.raises(EvaluationError, match="Unknown function: FooBar"):
            evaluator.evaluate(node, sample_data)

    def test_wrong_arg_count_mean(self, evaluator: ExprEvaluator, sample_data: pd.DataFrame):
        node = CallNode("Mean", (FeatureNode("close"),))
        with pytest.raises(EvaluationError, match="Mean expects 2 args, got 1"):
            evaluator.evaluate(node, sample_data)

    def test_wrong_arg_count_rank(self, evaluator: ExprEvaluator, sample_data: pd.DataFrame):
        node = CallNode("Rank", (FeatureNode("close"), LiteralNode(5)))
        with pytest.raises(EvaluationError, match="Rank expects 1 args, got 2"):
            evaluator.evaluate(node, sample_data)

    def test_non_literal_window(self, evaluator: ExprEvaluator, sample_data: pd.DataFrame):
        node = CallNode("Mean", (FeatureNode("close"), FeatureNode("volume")))
        with pytest.raises(EvaluationError, match="window argument must be a literal"):
            evaluator.evaluate(node, sample_data)


# ---------------------------------------------------------------------------
# Output shape & immutability
# ---------------------------------------------------------------------------

class TestOutputContract:
    def test_output_has_factor_column(self, evaluator: ExprEvaluator, sample_data: pd.DataFrame):
        result = evaluator.evaluate(FeatureNode("close"), sample_data)
        assert list(result.columns) == ["factor"]

    def test_output_index_matches_input(self, evaluator: ExprEvaluator, sample_data: pd.DataFrame):
        result = evaluator.evaluate(FeatureNode("close"), sample_data)
        assert result.index.equals(sample_data.index)

    def test_input_data_not_mutated(self, evaluator: ExprEvaluator, sample_data: pd.DataFrame):
        original = sample_data.copy()
        node = CallNode("Mean", (FeatureNode("close"), LiteralNode(5)))
        evaluator.evaluate(node, sample_data)
        pd.testing.assert_frame_equal(sample_data, original)
