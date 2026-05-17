"""Tests for the factor expression parser. 30+ cases covering valid, invalid, and edge cases."""

import pytest

from alpha_agent.factor_engine.ast_nodes import (
    BinaryOpNode,
    CallNode,
    FeatureNode,
    LiteralNode,
    UnaryOpNode,
)
from alpha_agent.factor_engine.parser import ExprParser, ParseError


@pytest.fixture
def parser() -> ExprParser:
    return ExprParser()


# --- Literals ---


class TestLiterals:
    def test_integer(self, parser: ExprParser) -> None:
        assert parser.parse("42") == LiteralNode(value=42.0)

    def test_float(self, parser: ExprParser) -> None:
        assert parser.parse("3.14") == LiteralNode(value=3.14)

    def test_decimal_starting_with_dot(self, parser: ExprParser) -> None:
        assert parser.parse(".5") == LiteralNode(value=0.5)

    def test_zero(self, parser: ExprParser) -> None:
        assert parser.parse("0") == LiteralNode(value=0.0)


# --- Features ---


class TestFeatures:
    def test_close(self, parser: ExprParser) -> None:
        assert parser.parse("$close") == FeatureNode(name="close")

    def test_volume(self, parser: ExprParser) -> None:
        assert parser.parse("$volume") == FeatureNode(name="volume")

    def test_open(self, parser: ExprParser) -> None:
        assert parser.parse("$open") == FeatureNode(name="open")

    def test_amount(self, parser: ExprParser) -> None:
        assert parser.parse("$amount") == FeatureNode(name="amount")


# --- Function calls ---


class TestCalls:
    def test_single_arg(self, parser: ExprParser) -> None:
        result = parser.parse("Rank($close)")
        assert result == CallNode(func_name="Rank", args=(FeatureNode(name="close"),))

    def test_two_args(self, parser: ExprParser) -> None:
        result = parser.parse("Delta($close, 5)")
        assert result == CallNode(
            func_name="Delta",
            args=(FeatureNode(name="close"), LiteralNode(value=5.0)),
        )

    def test_three_args(self, parser: ExprParser) -> None:
        result = parser.parse("Corr($close, $volume, 20)")
        assert result == CallNode(
            func_name="Corr",
            args=(
                FeatureNode(name="close"),
                FeatureNode(name="volume"),
                LiteralNode(value=20.0),
            ),
        )

    def test_nested_call(self, parser: ExprParser) -> None:
        result = parser.parse("Rank(Delta($close, 5))")
        inner = CallNode(
            func_name="Delta",
            args=(FeatureNode(name="close"), LiteralNode(value=5.0)),
        )
        assert result == CallNode(func_name="Rank", args=(inner,))

    def test_deeply_nested(self, parser: ExprParser) -> None:
        result = parser.parse("Rank(Abs(Delta($close, 5)))")
        delta = CallNode(
            func_name="Delta",
            args=(FeatureNode(name="close"), LiteralNode(value=5.0)),
        )
        abs_call = CallNode(func_name="Abs", args=(delta,))
        assert result == CallNode(func_name="Rank", args=(abs_call,))


# --- Infix operators ---


class TestInfix:
    def test_addition(self, parser: ExprParser) -> None:
        result = parser.parse("$close + $open")
        assert result == BinaryOpNode(
            op="+", left=FeatureNode(name="close"), right=FeatureNode(name="open")
        )

    def test_subtraction(self, parser: ExprParser) -> None:
        result = parser.parse("$close - $open")
        assert result == BinaryOpNode(
            op="-", left=FeatureNode(name="close"), right=FeatureNode(name="open")
        )

    def test_multiplication(self, parser: ExprParser) -> None:
        result = parser.parse("$close * 2")
        assert result == BinaryOpNode(
            op="*", left=FeatureNode(name="close"), right=LiteralNode(value=2.0)
        )

    def test_division(self, parser: ExprParser) -> None:
        result = parser.parse("$close / $open")
        assert result == BinaryOpNode(
            op="/", left=FeatureNode(name="close"), right=FeatureNode(name="open")
        )

    def test_power(self, parser: ExprParser) -> None:
        result = parser.parse("$close ** 2")
        assert result == BinaryOpNode(
            op="**", left=FeatureNode(name="close"), right=LiteralNode(value=2.0)
        )

    def test_precedence_mul_over_add(self, parser: ExprParser) -> None:
        # $close + $open * $volume => $close + ($open * $volume)
        result = parser.parse("$close + $open * $volume")
        assert result == BinaryOpNode(
            op="+",
            left=FeatureNode(name="close"),
            right=BinaryOpNode(
                op="*", left=FeatureNode(name="open"), right=FeatureNode(name="volume")
            ),
        )

    def test_precedence_with_parens(self, parser: ExprParser) -> None:
        # ($close + $open) * $volume
        result = parser.parse("($close + $open) * $volume")
        assert result == BinaryOpNode(
            op="*",
            left=BinaryOpNode(
                op="+", left=FeatureNode(name="close"), right=FeatureNode(name="open")
            ),
            right=FeatureNode(name="volume"),
        )

    def test_left_associativity(self, parser: ExprParser) -> None:
        # 1 - 2 - 3 => (1 - 2) - 3
        result = parser.parse("1 - 2 - 3")
        assert result == BinaryOpNode(
            op="-",
            left=BinaryOpNode(
                op="-", left=LiteralNode(value=1.0), right=LiteralNode(value=2.0)
            ),
            right=LiteralNode(value=3.0),
        )

    def test_comparison_gt(self, parser: ExprParser) -> None:
        result = parser.parse("$close > $open")
        assert result == BinaryOpNode(
            op=">", left=FeatureNode(name="close"), right=FeatureNode(name="open")
        )

    def test_comparison_gte(self, parser: ExprParser) -> None:
        result = parser.parse("$close >= 100")
        assert result == BinaryOpNode(
            op=">=", left=FeatureNode(name="close"), right=LiteralNode(value=100.0)
        )


# --- Unary operations ---


class TestUnary:
    def test_negate_feature(self, parser: ExprParser) -> None:
        result = parser.parse("-$close")
        assert result == UnaryOpNode(op="-", operand=FeatureNode(name="close"))

    def test_negate_call(self, parser: ExprParser) -> None:
        result = parser.parse("-Delta($close, 5)")
        inner = CallNode(
            func_name="Delta",
            args=(FeatureNode(name="close"), LiteralNode(value=5.0)),
        )
        assert result == UnaryOpNode(op="-", operand=inner)

    def test_double_negate(self, parser: ExprParser) -> None:
        result = parser.parse("--$close")
        assert result == UnaryOpNode(
            op="-", operand=UnaryOpNode(op="-", operand=FeatureNode(name="close"))
        )


# --- Complex real-world expressions ---


class TestRealWorld:
    def test_zscore(self, parser: ExprParser) -> None:
        """($close - Mean($close, 20)) / Std($close, 20)"""
        result = parser.parse("($close - Mean($close, 20)) / Std($close, 20)")
        assert isinstance(result, BinaryOpNode)
        assert result.op == "/"
        assert isinstance(result.left, BinaryOpNode)
        assert result.left.op == "-"
        assert isinstance(result.right, CallNode)
        assert result.right.func_name == "Std"

    def test_reversal_factor(self, parser: ExprParser) -> None:
        """Rank(-Delta($close, 5))"""
        result = parser.parse("Rank(-Delta($close, 5))")
        assert isinstance(result, CallNode)
        assert result.func_name == "Rank"
        inner = result.args[0]
        assert isinstance(inner, UnaryOpNode)
        assert isinstance(inner.operand, CallNode)
        assert inner.operand.func_name == "Delta"

    def test_momentum_factor(self, parser: ExprParser) -> None:
        """Rank($close / Ref($close, 5) - 1)"""
        result = parser.parse("Rank($close / Ref($close, 5) - 1)")
        assert isinstance(result, CallNode)
        assert result.func_name == "Rank"

    def test_mixed_infix_and_calls(self, parser: ExprParser) -> None:
        """Mean($close, 5) + Mean($open, 5)"""
        result = parser.parse("Mean($close, 5) + Mean($open, 5)")
        assert isinstance(result, BinaryOpNode)
        assert result.op == "+"
        assert isinstance(result.left, CallNode)
        assert isinstance(result.right, CallNode)

    def test_conditional_expression(self, parser: ExprParser) -> None:
        """If($close > $open, $volume, 0)"""
        result = parser.parse("If($close > $open, $volume, 0)")
        assert isinstance(result, CallNode)
        assert result.func_name == "If"
        assert len(result.args) == 3
        assert isinstance(result.args[0], BinaryOpNode)
        assert result.args[0].op == ">"


# --- Whitespace handling ---


class TestWhitespace:
    def test_no_spaces(self, parser: ExprParser) -> None:
        result = parser.parse("Rank(Delta($close,5))")
        assert isinstance(result, CallNode)

    def test_extra_spaces(self, parser: ExprParser) -> None:
        result = parser.parse("  Rank(  Delta( $close ,  5 )  )  ")
        assert isinstance(result, CallNode)


# --- Error cases ---


class TestErrors:
    def test_empty_string(self, parser: ExprParser) -> None:
        with pytest.raises(ParseError):
            parser.parse("")

    def test_unclosed_paren(self, parser: ExprParser) -> None:
        with pytest.raises(ParseError):
            parser.parse("(1 + 2")

    def test_missing_arg(self, parser: ExprParser) -> None:
        with pytest.raises(ParseError):
            parser.parse("Rank()")

    def test_trailing_operator(self, parser: ExprParser) -> None:
        with pytest.raises(ParseError):
            parser.parse("$close +")

    def test_double_operator(self, parser: ExprParser) -> None:
        with pytest.raises(ParseError):
            parser.parse("$close ++ $open")

    def test_invalid_character(self, parser: ExprParser) -> None:
        with pytest.raises(ParseError):
            parser.parse("$close @ $open")

    def test_bare_feature_is_valid(self, parser: ExprParser) -> None:
        # bare "close" is now a valid feature (no $ needed)
        result = parser.parse("close")
        assert isinstance(result, FeatureNode)
        assert result.name == "close"

    def test_unknown_bare_ident_requires_parens(self, parser: ExprParser) -> None:
        # bare "foo" is not a known feature, so it's treated as a function call
        with pytest.raises(ParseError):
            parser.parse("foo")

    def test_trailing_comma(self, parser: ExprParser) -> None:
        with pytest.raises(ParseError):
            parser.parse("Mean($close, 5,)")
