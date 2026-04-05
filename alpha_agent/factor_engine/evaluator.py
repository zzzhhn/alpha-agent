"""Evaluate a factor expression AST against a stock market DataFrame.

The evaluator walks an AST (defined in ast_nodes.py) and produces a
single-column "factor" DataFrame with the same MultiIndex (date, stock_code).

Key invariant: time-series operators group by stock_code, cross-sectional
operators group by date.  Input data is never mutated.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from alpha_agent.factor_engine.ast_nodes import (
    BinaryOpNode,
    CallNode,
    ExprNode,
    FeatureNode,
    LiteralNode,
    UnaryOpNode,
)

if TYPE_CHECKING:
    pass

class EvaluationError(Exception):
    """Raised when an expression cannot be evaluated."""

# Operator registries: func_name -> expected arg count
_TS_ONE_ARG: dict[str, int] = {
    "Mean": 2, "Sum": 2, "Std": 2, "Var": 2, "Max": 2, "Min": 2,
    "Skew": 2, "Kurt": 2, "Med": 2, "EMA": 2, "WMA": 2,
    "Ref": 2, "Delta": 2, "Slope": 2, "Count": 2,
}
_TS_TWO_ARG: dict[str, int] = {"Corr": 3, "Cov": 3}
_CS_OPS: set[str] = {"Rank", "Zscore"}
_ELEM_OPS: set[str] = {"Abs", "Sign", "Log"}
_COND_OPS: set[str] = {"If"}
_BINARY_OPS: set[str] = {"+", "-", "*", "/", "**", ">", "<", ">=", "<="}


def _to_series(value: pd.Series | float | int, index: pd.MultiIndex) -> pd.Series:
    """Ensure *value* is a Series aligned to *index*."""
    if isinstance(value, pd.Series):
        return value
    return pd.Series(value, index=index, dtype=float)


def _ts_apply(
    series: pd.Series, func: callable,  # noqa: ANN001
) -> pd.Series:
    """Apply *func* per stock group, fixing the extra index level that
    ``groupby.apply`` adds on a MultiIndex Series."""
    result = series.groupby(level="stock_code").apply(func)
    # groupby.apply prepends the group key → 3-level index; drop level 0
    if result.index.nlevels > series.index.nlevels:
        result = result.droplevel(0)
    return result.reindex(series.index)


class ExprEvaluator:
    """Walk an AST and evaluate it against a MultiIndex stock DataFrame."""

    def evaluate(self, node: ExprNode, data: pd.DataFrame) -> pd.DataFrame:
        """Return a DataFrame with column ``factor`` and the same index as *data*."""
        series = self._eval(node, data)
        result = _to_series(series, data.index).rename("factor")
        return result.to_frame()

    # -- recursive dispatch ------------------------------------------------

    def _eval(self, node: ExprNode, data: pd.DataFrame) -> pd.Series | float:
        match node:
            case LiteralNode(value=v):
                return v
            case FeatureNode(name=name):
                return self._eval_feature(name, data)
            case UnaryOpNode(op="-", operand=child):
                return -_to_series(self._eval(child, data), data.index)
            case BinaryOpNode(op=op, left=left, right=right):
                return self._eval_binary(op, left, right, data)
            case CallNode(func_name=fname, args=args):
                return self._eval_call(fname, args, data)
            case _:
                raise EvaluationError(f"Unknown node type: {type(node).__name__}")

    # -- features ----------------------------------------------------------

    @staticmethod
    def _eval_feature(name: str, data: pd.DataFrame) -> pd.Series:
        if name not in data.columns:
            raise EvaluationError(
                f"Feature '{name}' not found. Available: {list(data.columns)}"
            )
        return data[name].copy()

    # -- binary ops --------------------------------------------------------

    def _eval_binary(
        self, op: str, left: ExprNode, right: ExprNode, data: pd.DataFrame
    ) -> pd.Series:
        if op not in _BINARY_OPS:
            raise EvaluationError(f"Unknown binary operator: {op}")
        lv = _to_series(self._eval(left, data), data.index)
        rv = _to_series(self._eval(right, data), data.index)
        match op:
            case "+":  return lv + rv
            case "-":  return lv - rv
            case "*":  return lv * rv
            case "/":  return lv / rv
            case "**": return lv ** rv
            case ">":  return (lv > rv).astype(float)
            case "<":  return (lv < rv).astype(float)
            case ">=": return (lv >= rv).astype(float)
            case "<=": return (lv <= rv).astype(float)
            case _:    raise EvaluationError(f"Unhandled op: {op}")  # pragma: no cover

    # -- function calls ----------------------------------------------------

    def _eval_call(
        self, fname: str, args: tuple[ExprNode, ...], data: pd.DataFrame
    ) -> pd.Series:
        # --- time-series, one expression arg + window ---
        if fname in _TS_ONE_ARG:
            self._check_argc(fname, args, _TS_ONE_ARG[fname])
            series = _to_series(self._eval(args[0], data), data.index)
            window = self._literal_int(args[1], fname)
            return self._ts_one_arg(fname, series, window, data)

        # --- time-series, two expression args + window ---
        if fname in _TS_TWO_ARG:
            self._check_argc(fname, args, _TS_TWO_ARG[fname])
            sx = _to_series(self._eval(args[0], data), data.index)
            sy = _to_series(self._eval(args[1], data), data.index)
            window = self._literal_int(args[2], fname)
            return self._ts_two_arg(fname, sx, sy, window, data)

        # --- cross-sectional ---
        if fname in _CS_OPS:
            self._check_argc(fname, args, 1)
            series = _to_series(self._eval(args[0], data), data.index)
            return self._cs_op(fname, series)

        # --- element-wise ---
        if fname in _ELEM_OPS:
            self._check_argc(fname, args, 1)
            series = _to_series(self._eval(args[0], data), data.index)
            return self._elem_op(fname, series)

        # --- conditional ---
        if fname in _COND_OPS:
            self._check_argc(fname, args, 3)
            cond = _to_series(self._eval(args[0], data), data.index)
            x = _to_series(self._eval(args[1], data), data.index)
            y = _to_series(self._eval(args[2], data), data.index)
            return pd.Series(np.where(cond, x, y), index=data.index)

        raise EvaluationError(f"Unknown function: {fname}")

    # -- time-series single-expression operators ---------------------------

    @staticmethod
    def _ts_one_arg(
        fname: str, series: pd.Series, window: int, data: pd.DataFrame
    ) -> pd.Series:
        grouped = series.groupby(level="stock_code")
        match fname:
            case "Ref":
                return grouped.shift(window)
            case "Delta":
                return series - grouped.shift(window)
            case "Mean":
                return _ts_apply(series, lambda g: g.rolling(window).mean())
            case "Sum":
                return _ts_apply(series, lambda g: g.rolling(window).sum())
            case "Std":
                return _ts_apply(series, lambda g: g.rolling(window).std())
            case "Var":
                return _ts_apply(series, lambda g: g.rolling(window).var())
            case "Max":
                return _ts_apply(series, lambda g: g.rolling(window).max())
            case "Min":
                return _ts_apply(series, lambda g: g.rolling(window).min())
            case "Skew":
                return _ts_apply(series, lambda g: g.rolling(window).skew())
            case "Kurt":
                return _ts_apply(series, lambda g: g.rolling(window).kurt())
            case "Med":
                return _ts_apply(series, lambda g: g.rolling(window).median())
            case "Count":
                return _ts_apply(series, lambda g: g.rolling(window).count())
            case "EMA":
                return _ts_apply(series, lambda g: g.ewm(span=window).mean())
            case "WMA":
                return _ts_apply(series, lambda g: _wma(g, window))
            case "Slope":
                return _ts_apply(series, lambda g: _slope(g, window))
            case _:
                raise EvaluationError(f"Unhandled ts op: {fname}")  # pragma: no cover

    # -- time-series two-expression operators ------------------------------

    @staticmethod
    def _ts_two_arg(
        fname: str,
        sx: pd.Series,
        sy: pd.Series,
        window: int,
        data: pd.DataFrame,
    ) -> pd.Series:
        match fname:
            case "Corr":
                return _ts_apply(
                    sx, lambda g: g.rolling(window).corr(sy.loc[g.index])
                )
            case "Cov":
                return _ts_apply(
                    sx, lambda g: g.rolling(window).cov(sy.loc[g.index])
                )
            case _:
                raise EvaluationError(f"Unhandled ts2 op: {fname}")  # pragma: no cover

    # -- cross-sectional operators -----------------------------------------

    @staticmethod
    def _cs_op(fname: str, series: pd.Series) -> pd.Series:
        match fname:
            case "Rank":
                return series.groupby(level="date").rank(pct=True)
            case "Zscore":
                grouped = series.groupby(level="date")
                mean = grouped.transform("mean")
                std = grouped.transform("std")
                return (series - mean) / std
            case _:
                raise EvaluationError(f"Unhandled cs op: {fname}")  # pragma: no cover

    # -- element-wise operators --------------------------------------------

    @staticmethod
    def _elem_op(fname: str, series: pd.Series) -> pd.Series:
        match fname:
            case "Abs":
                return series.abs()
            case "Sign":
                return pd.Series(np.sign(series), index=series.index)
            case "Log":
                return pd.Series(np.log(series), index=series.index)
            case _:
                raise EvaluationError(f"Unhandled elem op: {fname}")  # pragma: no cover

    # -- validation helpers ------------------------------------------------

    @staticmethod
    def _check_argc(fname: str, args: tuple[ExprNode, ...], expected: int) -> None:
        if len(args) != expected:
            raise EvaluationError(
                f"{fname} expects {expected} args, got {len(args)}"
            )

    @staticmethod
    def _literal_int(node: ExprNode, context: str) -> int:
        if not isinstance(node, LiteralNode):
            raise EvaluationError(
                f"{context}: window argument must be a literal, "
                f"got {type(node).__name__}"
            )
        return int(node.value)


def _wma(series: pd.Series, window: int) -> pd.Series:
    """Weighted moving average with linearly increasing weights [1, 2, ..., d]."""
    weights = np.arange(1, window + 1, dtype=float)
    weight_sum = weights.sum()
    return series.rolling(window).apply(
        lambda x: np.dot(x, weights) / weight_sum, raw=True
    )


def _slope(series: pd.Series, window: int) -> pd.Series:
    """Linear regression slope over a rolling window."""
    x = np.arange(window, dtype=float)
    x_mean = x.mean()
    x_var = ((x - x_mean) ** 2).sum()

    def _calc(y: np.ndarray) -> float:
        return np.dot(y - y.mean(), x - x_mean) / x_var

    return series.rolling(window).apply(_calc, raw=True)
