"""Phase 3c extra_ops dispatch hook tests."""
import numpy as np
import pandas as pd
import pytest

from alpha_agent.factor_engine.evaluator import ExprEvaluator
from alpha_agent.factor_engine.parser import ExprParser


def _parse(expr: str):
    return ExprParser().parse(expr)


def _panel():
    """Minimal MultiIndex panel: 1 ticker, 4 days, one column close."""
    idx = pd.MultiIndex.from_product([range(4), ["AAPL"]], names=["date", "stock_code"])
    return pd.DataFrame({"close": [1.0, 2.0, 3.0, 4.0]}, index=idx)


def test_evaluator_dispatches_to_extra_ops_when_name_not_builtin():
    """When the AST hits an unknown call name, extra_ops resolves it."""
    panel = _panel()
    node = _parse("lf_double(close)")
    def lf_double(x):
        return x * 2
    ev = ExprEvaluator(extra_ops={"lf_double": lf_double})
    result = ev.evaluate(node, panel)
    assert isinstance(result, pd.DataFrame)
    assert "factor" in result.columns
    assert result["factor"].tolist() == [2.0, 4.0, 6.0, 8.0]


def test_evaluator_still_raises_for_truly_unknown_op():
    panel = _panel()
    node = _parse("lf_totally_unknown(close)")
    ev = ExprEvaluator(extra_ops={"lf_known": lambda x: x})
    with pytest.raises(Exception):  # EvaluationError or similar
        ev.evaluate(node, panel)


def test_extra_ops_does_not_shadow_builtins():
    """Built-in `rank` (Rank in the AST grammar) always wins over an extra_ops
    entry of the same name. Affordance UX: admins cannot accidentally break
    built-ins by proposing a same-named operator."""
    panel = _panel()
    node = _parse("Rank(close)")
    # Override Rank with a "return zeros" sabotage attempt:
    ev = ExprEvaluator(extra_ops={"Rank": lambda x: pd.Series(np.zeros(len(x)), index=x.index)})
    result = ev.evaluate(node, panel)
    # Built-in Rank produces a non-zero rank series; extra_ops was IGNORED.
    assert not (result["factor"] == 0.0).all()


def test_evaluator_with_no_extra_ops_unchanged():
    """ExprEvaluator() with no arg is the backward-compat default; pure
    backward compat with all existing call sites."""
    panel = _panel()
    node = _parse("Rank(close)")
    ev = ExprEvaluator()  # no extra_ops kwarg
    result = ev.evaluate(node, panel)
    assert isinstance(result, pd.DataFrame)
    assert "factor" in result.columns
