import pytest

from alpha_agent.evolution.expression_canonical import canonical_expression


@pytest.mark.parametrize(("expression", "expected"), [
    ("rank( close )", "rank(close)"),
    (" \n rank(close) \t", "rank(close)"),
    ("ts_mean( close,20 )", "ts_mean(close, 20)"),
    ("ts_mean(close ,   20)", "ts_mean(close, 20)"),
    ("group_neutralize( zscore(ts_zscore(volume,20)),sector )",
     "group_neutralize(zscore(ts_zscore(volume, 20)), sector)"),
    ("ts_mean(close, +20.0)", "ts_mean(close, 20)"),
    ("custom( close, 20 )", "custom(close, 20)"),
    ("broken( close,20", "broken(close, 20"),
    ("close   +   volume", "close + volume"),
    ("rank( close, window=20 )", "rank(close, window=20)"),
    ("", ""),
])
def test_canonical_expression(expression, expected):
    assert canonical_expression(expression) == expected
    assert canonical_expression(expected) == expected


def test_canonical_expression_does_not_drop_keyword_arguments():
    assert canonical_expression("rank(close, window=20)") != canonical_expression("rank(close)")
