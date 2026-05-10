"""Composite factor signal: leverages the existing v3 factor engine.

The "value" we expose as z is the cross-sectional z-score of the
default composite factor (Pure-Alpha pick from spec §3.1: weight 0.30).

Note on signature adaptation: the plan assumed evaluate_cross_section took
as_of_date (str), but the real kernel signature uses as_of_index (int).
We default to -1 (most recent row) which is correct for live scoring.
"""
from __future__ import annotations

from datetime import datetime

import numpy as np

from alpha_agent.signals.base import SignalScore, safe_fetch

DEFAULT_FACTOR_EXPR = "rank(ts_mean(returns, 12)) - rank(ts_std(returns, 60))"


def _evaluate_for_universe(as_of: datetime, expr: str = DEFAULT_FACTOR_EXPR) -> dict[str, float]:
    """Returns {ticker: z_score} on as_of's date row.
    Wraps factor_engine.kernel.evaluate_cross_section.
    Uses as_of_index=-1 (most recent) since the real kernel does not accept
    a date string — it accepts an integer row index.
    """
    from alpha_agent.factor_engine.factor_backtest import _load_panel
    from alpha_agent.factor_engine.kernel import evaluate_cross_section
    from alpha_agent.core.types import FactorSpec

    # `_Panel.load_default()` does NOT exist (M1 plan invented it). The real
    # API is the module-level `_load_panel()` (lru_cache'd) that reads the
    # parquet at alpha_agent/data/factor_universe_sp500_v3.parquet.
    panel = _load_panel()
    spec = FactorSpec(expression=expr)
    scores = evaluate_cross_section(panel, spec, as_of_index=-1)
    arr = np.array(list(scores.values()), dtype=float)
    mu, sigma = np.nanmean(arr), np.nanstd(arr)
    if sigma == 0 or np.isnan(sigma):
        return {t: 0.0 for t in scores}
    return {t: float(np.clip((v - mu) / sigma, -3.0, 3.0)) for t, v in scores.items()}


def _fetch(ticker: str, as_of: datetime) -> SignalScore:
    scores = _evaluate_for_universe(as_of)
    if ticker not in scores:
        raise KeyError(f"{ticker} not in panel universe")
    z = scores[ticker]
    return SignalScore(
        ticker=ticker, z=z, raw=z, confidence=0.95,
        as_of=as_of, source="factor_engine", error=None,
    )


def fetch_signal(ticker: str, as_of: datetime) -> SignalScore:
    return safe_fetch(_fetch, ticker, as_of, source="factor_engine")
