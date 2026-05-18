"""Composite factor signal: leverages the existing v3 factor engine.

The "value" we expose as z is the cross-sectional z-score of the
default composite factor (Pure-Alpha pick from spec §3.1: weight 0.30).

Academic anchors (2020-2025 modernization, 2026-05-18):
- Momentum leg: Jegadeesh-Titman (1993) classic, refined as 12-1 in
  Asness-Moskowitz-Pedersen (2013, JoF) "Value & Momentum Everywhere".
- Vol leg: Frazzini-Pedersen (2014, JFE) "Betting Against Beta" formalizes
  the defensive premium; Daniel-Moskowitz (2016, JFE) "Momentum Crashes"
  motivates the 6-month vol scaling that crash-hedges momentum strategies.
- Composite construction philosophy: Asness-Frazzini-Pedersen (2013) JFE
  "The Devil in HML's Details" — discusses rank-then-combine vs raw-then-z
  trade-offs that our rank()/subtract pattern follows.
- Phase X TBD upgrades (deferred until operator + data infra extends):
  Asness-Frazzini-Pedersen (2019, RAR) "Quality Minus Junk" for a QMJ
  factor leg; Hou-Xue-Zhang (2015, RFS) q-factor for composite weighting.

M4a: raw payload upgraded from `float` (just the z score) to
`{z: float, fundamentals: dict | None}` so FundamentalsBlock has real
P/E, market cap, dividend yield etc. to render without a separate
per-page fetch. yfinance is the data source (already in deps, no key).
"""
from __future__ import annotations

import os
from datetime import datetime

import numpy as np

from alpha_agent.signals.base import SignalScore, safe_fetch
from alpha_agent.signals.yf_helpers import extract_fundamentals, get_ticker

# Two factor expressions coexist (added 2026-05-18 after user feedback):
#
# 1. SHORT_TERM_FACTOR_EXPR — original 12d momentum + 60d vol blend. Suited
#    for swing trading (days to ~2 weeks holding) and intraday-adjacent
#    rotation strategies. This is the platform's historical default and the
#    one most users actually trade against because the news/technicals/
#    premarket signals in the composite are also short-window.
#
# 2. LONG_TERM_FACTOR_EXPR — 252d momentum + 126d vol per the 2026-05-18
#    academic modernization (Jegadeesh-Titman 1993 / Asness-Moskowitz-Pedersen
#    2013 "Value & Momentum Everywhere" 12-month momentum + Daniel-Moskowitz
#    2016 / Frazzini-Pedersen 2014 6-month vol crash-hedge). Suited for
#    monthly-to-quarterly position holding where the academic literature is
#    well-validated. The classic 12-1 skip is Phase X TBD (needs ts_delay in
#    the expression DSL).
#
# Active mode is controlled by ALPHA_FACTOR_MODE env var:
#   "short" (default): use SHORT_TERM_FACTOR_EXPR — matches the rest of the
#                       composite's short-window signals (news 24h, technicals
#                       daily, premarket overnight, earnings 14d decay).
#   "long":            use LONG_TERM_FACTOR_EXPR — for users running a more
#                       academic/medium-term framework.
#
# Function-call form (subtract/rank/ts_mean/ts_std) is required because the
# factor engine AST only accepts function calls, not BinOp nodes. Production
# cron was silently producing factor.raw=null until M4a F1 smoke caught this.
#
# Phase 2 TBD: surface a per-user UI toggle (Picks/Stock header) that flips
# this env-var-driven default. Requires (a) fast_intraday cron to compute
# BOTH factor_short_z and factor_long_z per ticker and persist both in
# breakdown.raw (so toggle is instant, no recompute), and (b) a user_settings
# table OR localStorage-backed preference. Until Phase 2 ships, env-var
# default applies platform-wide.
SHORT_TERM_FACTOR_EXPR = (
    "subtract(rank(ts_mean(returns, 12)), rank(ts_std(returns, 60)))"
)
LONG_TERM_FACTOR_EXPR = (
    "subtract(rank(ts_mean(returns, 252)), rank(ts_std(returns, 126)))"
)


def _resolve_default_expr() -> str:
    """Resolve the active factor expression from ALPHA_FACTOR_MODE env var.
    Defaults to 'short' (the platform's historical default + the only mode
    that aligns with the rest of the short-window signal composite).

    Reads env on every call so tests + per-invocation overrides work. The
    env lookup is sub-microsecond so cost is negligible vs the factor
    panel evaluation that follows."""
    mode = os.environ.get("ALPHA_FACTOR_MODE", "short").strip().lower()
    return LONG_TERM_FACTOR_EXPR if mode == "long" else SHORT_TERM_FACTOR_EXPR


# Backward-compat alias: existing imports + tests that reference
# DEFAULT_FACTOR_EXPR keep working. New code should call _resolve_default_expr()
# or pass an explicit `expr` to _evaluate_for_universe.
DEFAULT_FACTOR_EXPR = _resolve_default_expr()


def _evaluate_for_universe(as_of: datetime, expr: str | None = None) -> dict[str, float]:
    """Returns {ticker: z_score} on as_of's date row.
    Wraps factor_engine.kernel.evaluate_cross_section.

    `expr` defaults to whatever ALPHA_FACTOR_MODE env var resolves to
    (short → SHORT_TERM_FACTOR_EXPR, long → LONG_TERM_FACTOR_EXPR).
    Explicit `expr` argument overrides the env var (used by screener,
    hypothesis lab, and Phase 2 per-user toggle).
    """
    if expr is None:
        expr = _resolve_default_expr()
    from alpha_agent.factor_engine.factor_backtest import _load_panel
    from alpha_agent.factor_engine.kernel import evaluate_cross_section
    from alpha_agent.core.types import FactorSpec

    panel = _load_panel()
    # FactorSpec requires 6 fields beyond expression. Surfaced by F1 smoke
    # against deployed /api/stock/AAPL: factor.raw was always null because
    # FactorSpec(expression=...) raised ValidationError, caught silently by
    # safe_fetch. B1 unit tests mocked _evaluate_for_universe entirely so
    # they didn't exercise this constructor — the FactorSpec regression
    # test below guards against drift.
    spec = FactorSpec(
        name="default_composite",
        hypothesis="Cross-sectional momentum minus volatility composite for SP500.",
        expression=expr,
        operators_used=["rank", "ts_mean", "ts_std", "subtract"],
        lookback=60,
        universe="SP500",
        justification="Default factor for Phase 1 fast cron when no user override is provided.",
    )
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
