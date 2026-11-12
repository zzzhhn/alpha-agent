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

from alpha_agent.config_store import get_config
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
    """Resolve the active factor expression. Precedence order (Phase 3a):
       1. factor.custom_expression knob (set by Phase 3d Approve when an LLM
          proposal lands). Non-empty string wins.
       2. factor.mode preset ("short" or "long") from config or env var.

    Reads on every call so tests + per-invocation overrides work."""
    custom = get_config("factor.custom_expression", None)
    if custom:  # non-None AND non-empty (forgiveness: empty string falls through)
        return custom
    mode = get_config("factor.mode", os.environ.get("ALPHA_FACTOR_MODE", "short")).strip().lower()
    return LONG_TERM_FACTOR_EXPR if mode == "long" else SHORT_TERM_FACTOR_EXPR


# Backward-compat alias: existing imports + tests that reference
# DEFAULT_FACTOR_EXPR keep working. New code should call _resolve_default_expr()
# or pass an explicit `expr` to _evaluate_for_universe.
DEFAULT_FACTOR_EXPR = _resolve_default_expr()


# Provenance of the most recent universe evaluation, so each emitted signal can
# disclose which expression it used and which panel row (data date) it read.
# A custom expression is evaluated on the frozen research parquet, not the live
# daily_prices panel; without this the UI cannot tell the factor is stale.
# Keyed by expression so the universe-wide long-mode evaluation in the same
# cron shard cannot overwrite the provenance of the default expression.
_LAST_EVAL: dict[str, dict[str, object]] = {}

# Live panel primed by the async cron entry points (fast_intraday, slow_daily)
# over the shared asyncpg pool. The serverless bundle has no psycopg, so the
# synchronous loader below always failed in production and every preset
# evaluation silently fell back to the frozen research parquet (2026-10-30).
_PRIMED_LIVE: dict[str, object] = {"panel": None, "info": {}}
# Cross-section scores per expression, valid only for the same panel object:
# the cron calls _fetch once per ticker and the universe need not be re-ranked
# each time. The panel itself is held so an identity match cannot be stale.
_SCORE_CACHE: dict[str, tuple[object, dict[str, float]]] = {}


async def prime_live_panel(pool) -> dict[str, object]:
    """Load the live daily_prices panel once per cron invocation.

    Returns a small receipt for logs. On failure the primed panel is cleared,
    so evaluation falls back to the frozen parquet and discloses it through
    ``factor_source.panel``."""
    from alpha_agent.factor_engine.factor_backtest import aload_live_panel

    _SCORE_CACHE.clear()
    try:
        panel, info = await aload_live_panel(pool, min_days=65)
    except Exception as exc:  # noqa: BLE001 — degrade to the disclosed parquet
        _PRIMED_LIVE.update(panel=None, info={})
        return {"live": False, "error_type": type(exc).__name__}
    _PRIMED_LIVE.update(panel=panel, info=info)
    dates = getattr(panel, "dates", None)
    return {
        "live": panel is not None,
        "data_date": str(dates[-1])[:10] if dates is not None and len(dates) else None,
        "excluded_suspect_jumps": len(info.get("excluded_suspect_jumps", [])),
    }


def factor_provenance(expr: str, panel, *, live: bool) -> dict[str, object]:
    """Pure helper: describe the expression and panel row actually evaluated."""
    dates = getattr(panel, "dates", None)
    data_date = str(dates[-1])[:10] if dates is not None and len(dates) else None
    return {
        "expression": expr,
        "is_custom": expr not in (SHORT_TERM_FACTOR_EXPR, LONG_TERM_FACTOR_EXPR),
        "panel": "live_daily_prices" if live else "frozen_research_parquet",
        "data_date": data_date,
    }


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
    from alpha_agent.factor_engine.factor_backtest import _load_panel, load_live_panel
    from alpha_agent.factor_engine.kernel import evaluate_cross_section
    from alpha_agent.core.types import FactorSpec

    # Prefer the LIVE panel (daily_prices, fresh every session) for the DEFAULT
    # SHORT expr so the 0.30-weight factor is never served from the frozen
    # parquet (it was ~50 trading days stale). Custom exprs and LONG mode (252d,
    # needs more history than daily_prices holds yet) stay on the parquet.
    panel = None
    live = False
    if expr == SHORT_TERM_FACTOR_EXPR:
        panel = _PRIMED_LIVE["panel"] or load_live_panel(min_days=65)
        live = panel is not None
    if panel is None:
        panel = _load_panel()
    provenance = factor_provenance(expr, panel, live=live)
    if live and panel is _PRIMED_LIVE["panel"]:
        provenance["excluded_suspect_jumps"] = list(
            _PRIMED_LIVE["info"].get("excluded_suspect_jumps", [])
        )
    cached = _SCORE_CACHE.get(expr)
    if cached is not None and cached[0] is panel:
        _LAST_EVAL[expr] = provenance
        return cached[1]
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
    _LAST_EVAL[expr] = provenance
    arr = np.array(list(scores.values()), dtype=float)
    mu, sigma = np.nanmean(arr), np.nanstd(arr)
    if sigma == 0 or np.isnan(sigma):
        out = {t: 0.0 for t in scores}
    else:
        out = {t: float(np.clip((v - mu) / sigma, -3.0, 3.0)) for t, v in scores.items()}
    _SCORE_CACHE[expr] = (panel, out)
    return out


def _fetch_info_for(ticker: str) -> dict:
    """Indirection so tests can patch the yfinance call without mocking
    the whole `get_ticker` chain."""
    return get_ticker(ticker).info or {}


def _fetch(ticker: str, as_of: datetime) -> SignalScore:
    expr = _resolve_default_expr()
    scores = _evaluate_for_universe(as_of, expr=expr)
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
        # factor_source discloses the evaluated expression and panel data date
        # (disclosure only; it does not change z or the fusion weights).
        raw={"z": z, "fundamentals": fundamentals, "factor_source": dict(_LAST_EVAL.get(expr) or {}) or None},
        confidence=0.95, as_of=as_of, source="factor_engine", error=None,
    )


def fetch_signal(ticker: str, as_of: datetime) -> SignalScore:
    return safe_fetch(_fetch, ticker, as_of, source="factor_engine")
