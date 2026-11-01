"""One bounded real-data context for generation, baseline and validation.

The bundled panel is a historical research dataset, NOT today's live data.
Never synthesize unavailable operands or splice dates to construct OOS folds.
"""
from __future__ import annotations

from dataclasses import dataclass, fields, replace
import json
from pathlib import Path

import numpy as np

from alpha_agent.factor_engine.factor_backtest import _Panel

VERSION = "real_panel_chronological_v1"
EMBARGO = 5
MIN_FOLD_DAYS = 15
MAX_SESSIONS = 504


class InvalidEvaluation(ValueError):
    def __init__(self, reason: str, detail: str = ""):
        self.reason = reason
        super().__init__(f"{reason}: {detail}")


def slice_panel(panel: _Panel, start: int = 0, end: int | None = None) -> _Panel:
    updates = {}
    for field in fields(panel):
        value = getattr(panel, field.name)
        if isinstance(value, np.ndarray):
            updates[field.name] = value[start:end]
        elif isinstance(value, dict):
            updates[field.name] = {k: v[start:end] for k, v in value.items()}
    return replace(panel, **updates)


@dataclass
class ResearchContext:
    panel: _Panel
    search_end: int
    folds: list[tuple[int, int]]
    coverage: dict[str, float]

    def evidence(self) -> dict:
        path = Path(__file__).resolve().parents[1] / "data/research_dataset.json"
        manifest = json.loads(path.read_text()) if path.exists() else {}
        return {
            "validator": VERSION,
            "source": "bundled_real_ohlcv_with_filing_date_fundamentals",
            "data_start": str(self.panel.dates[0]),
            "data_end": str(self.panel.dates[-1]),
            "search_end": str(self.panel.dates[self.search_end - 1]),
            "tickers": len(self.panel.tickers),
            "sessions": len(self.panel.dates),
            "dataset": manifest,
            "folds": [{"start": str(self.panel.dates[a]), "end": str(self.panel.dates[b - 1])}
                      for a, b in self.folds],
            "cost_bps_per_side": 10,
            "borrow_bps_per_year": 100,
            "limitations": ["historical_dataset_not_live", "sector_classification_snapshot",
                            "fundamentals_expire_after_200_days", "adjusted_prices_not_point_in_time_vintages",
                            "reused_holdout_not_independent_forward_test",
                            "daily_vwap_is_typical_price_proxy"],
        }


def context_from_panel(panel: _Panel) -> ResearchContext:
    from alpha_agent.factor_engine.kernel import build_data_dict

    dates = np.asarray(panel.dates, dtype="datetime64[D]")
    if len(dates) < 150 or np.any(dates[1:] <= dates[:-1]):
        raise InvalidEvaluation("invalid_timeline", "need >=150 strictly chronological sessions")
    if len(panel.tickers) < 10 or len(panel.benchmark_close) != len(dates):
        raise InvalidEvaluation("invalid_panel_shape")
    if not np.all(np.isfinite(panel.benchmark_close) & (panel.benchmark_close > 0)):
        raise InvalidEvaluation("missing_benchmark")
    search_end = int(len(dates) * 0.6)
    bounds = np.linspace(search_end, len(dates), 4).astype(int)
    # Return rows and IC labels stay within their own contiguous held-out block.
    folds = [(int(a + EMBARGO), int(b - 1)) for a, b in zip(bounds[:-1], bounds[1:])]
    if any(b - a < MIN_FOLD_DAYS for a, b in folds):
        raise InvalidEvaluation("history_too_short")
    coverage = {}
    for key, values in build_data_dict(panel).items():
        if values.dtype.kind in "OUS":
            valid = ~np.isin(values.astype(str), ["", "None", "nan", "Unknown", "unknown"])
        else:
            valid = np.isfinite(values)
        if panel.is_member is not None:
            valid = valid & panel.is_member
            denominator = max(1, int(panel.is_member.sum()))
        else:
            denominator = valid.size
        coverage[key] = float(valid.sum() / denominator)
    return ResearchContext(panel, search_end, folds, coverage)


def load_research_context() -> ResearchContext:
    from alpha_agent.factor_engine.factor_backtest import PIT_FUNDAMENTALS_PATH, _load_panel

    if not PIT_FUNDAMENTALS_PATH.exists():
        raise InvalidEvaluation("pit_fundamentals_unavailable", "snapshot fallback prohibited")
    panel = _load_panel()
    if panel.is_member is None:
        raise InvalidEvaluation("membership_unavailable")
    return context_from_panel(slice_panel(panel, max(0, len(panel.dates) - MAX_SESSIONS)))


def required_operands(expression: str) -> set[str]:
    from alpha_agent.core.factor_ast import expression_to_tree

    def walk(node):
        if node.get("type") == "operand":
            yield node["name"]
        for child in node.get("args", []):
            yield from walk(child)
    return set(walk(expression_to_tree(expression)))


def check_operands(context: ResearchContext, expression: str) -> None:
    missing = {name: round(context.coverage.get(name, 0), 3)
               for name in required_operands(expression)
               if context.coverage.get(name, 0) < 0.6}
    if missing:
        raise InvalidEvaluation("insufficient_operand_coverage", str(missing))


def score_expression(context: ResearchContext, expression: str, *, extra_ops=None):
    from alpha_agent.core.types import FactorSpec
    from alpha_agent.factor_engine.kernel import (
        KernelParams, evaluate_factor_full, run_kernel, spearman_ic, split_metrics,
    )

    check_operands(context, expression)
    spec = FactorSpec(name="research_validation", hypothesis="historical validation",
                      expression=expression, operators_used=[], lookback=120,
                      universe="SP500", justification="chronological held-out blocks")
    # One full chronological pass. No train/test concatenation and no date rewriting.
    params = KernelParams(direction="long_short", train_ratio=0.6,
                          transaction_cost_bps=10, short_borrow_bps=100,
                          purge_days=EMBARGO, embargo_days=EMBARGO)
    try:
        kr = run_kernel(context.panel, spec, params, extra_ops=extra_ops)
        if extra_ops:
            prefix = evaluate_factor_full(slice_panel(context.panel, 0, context.search_end),
                                          spec, extra_ops)
            if not np.allclose(prefix, kr.factor[:context.search_end], equal_nan=True):
                raise InvalidEvaluation("noncausal_operator", "future rows change earlier values")
    except InvalidEvaluation:
        raise
    except Exception as exc:
        raise InvalidEvaluation("kernel_exception", f"{type(exc).__name__}: {exc}") from exc
    sharpes, ics = [], []
    for start, end in context.folds:
        f = kr.factor[start:end]
        usable = (np.isfinite(f).sum(axis=1) >= 10) & (np.nanstd(f, axis=1) > 1e-12)
        if usable.sum() < MIN_FOLD_DAYS or usable.mean() < 0.8:
            raise InvalidEvaluation("insufficient_factor_coverage", f"fold {start}:{end}")
        held = np.abs(kr.weights[start:end])
        missing = (~np.isfinite(kr.fwd_returns[start:end])) * held
        if np.any(missing.sum(axis=1) > 0.02):
            raise InvalidEvaluation("missing_held_returns", f"fold {start}:{end}")
        metrics = split_metrics(kr.daily_ret, kr.factor, kr.fwd_returns, kr.weights,
                                start=start + 1, end=end, n_trials=1)
        ic = [spearman_ic(kr.factor[t], kr.fwd_returns[t]) for t in range(start, end - 1)]
        ic = [v for v in ic if np.isfinite(v)]
        if not np.isfinite(metrics.sharpe) or len(ic) < MIN_FOLD_DAYS:
            raise InvalidEvaluation("invalid_fold_metrics", f"fold {start}:{end}")
        sharpes.append(float(metrics.sharpe))
        ics.append(float(np.mean(ic)))
    return sharpes, float(np.mean(ics)), kr
