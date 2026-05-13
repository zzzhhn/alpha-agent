"""Composite factor signal: leverages the existing v3 factor engine.

The "value" we expose as z is the cross-sectional z-score of the
default composite factor (Pure-Alpha pick from spec §3.1: weight 0.30).

M4a: raw payload upgraded from `float` (just the z score) to
`{z: float, fundamentals: dict | None}` so FundamentalsBlock has real
P/E, market cap, dividend yield etc. to render without a separate
per-page fetch. yfinance is the data source (already in deps, no key).
"""
from __future__ import annotations

from datetime import datetime

import numpy as np

from alpha_agent.signals.base import SignalScore, safe_fetch
from alpha_agent.signals.yf_helpers import extract_fundamentals, get_ticker

DEFAULT_FACTOR_EXPR = "rank(ts_mean(returns, 12)) - rank(ts_std(returns, 60))"


def _evaluate_for_universe(as_of: datetime, expr: str = DEFAULT_FACTOR_EXPR) -> dict[str, float]:
    """Returns {ticker: z_score} on as_of's date row.
    Wraps factor_engine.kernel.evaluate_cross_section.
    """
    from alpha_agent.factor_engine.factor_backtest import _load_panel
    from alpha_agent.factor_engine.kernel import evaluate_cross_section
    from alpha_agent.core.types import FactorSpec

    panel = _load_panel()
    spec = FactorSpec(expression=expr)
    scores = evaluate_cross_section(panel, spec, as_of_index=-1)
    arr = np.array(list(scores.values()), dtype=float)
    mu, sigma = np.nanmean(arr), np.nanstd(arr)
    if sigma == 0 or np.isnan(sigma):
        return {t: 0.0 for t in scores}
    return {t: float(np.clip((v - mu) / sigma, -3.0, 3.0)) for t, v in scores.items()}


def _fetch_info_for(ticker: str) -> dict:
    """Indirection so tests can patch the yfinance call without mocking
    the whole `get_ticker` chain."""
    return get_ticker(ticker).info or {}


def _fetch(ticker: str, as_of: datetime) -> SignalScore:
    scores = _evaluate_for_universe(as_of)
    if ticker not in scores:
        raise KeyError(f"{ticker} not in panel universe")
    z = scores[ticker]

    # Best-effort fundamentals enrichment. If yfinance is rate-limited or
    # the ticker has sparse `info` (small caps), we still return the z;
    # the UI block falls back to "—" cells.
    try:
        info = _fetch_info_for(ticker)
        fundamentals = extract_fundamentals(info)
    except (KeyError, ValueError, ConnectionError, TimeoutError):
        fundamentals = None

    return SignalScore(
        ticker=ticker, z=z,
        raw={"z": z, "fundamentals": fundamentals},
        confidence=0.95, as_of=as_of, source="factor_engine", error=None,
    )


def fetch_signal(ticker: str, as_of: datetime) -> SignalScore:
    return safe_fetch(_fetch, ticker, as_of, source="factor_engine")
