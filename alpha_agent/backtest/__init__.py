"""Backtest sub-package — factor evaluation engine and metrics."""

from alpha_agent.backtest.engine import BacktestEngine
from alpha_agent.backtest.metrics import BacktestResult

__all__ = ["BacktestEngine", "BacktestResult"]
