"""Per-factor simulation-settings adaptation (the 'smart retry').

A single fixed settings config leaves Sharpe / turnover on the table: the SAME
expression flips fail->pass with the right decay / neutralization / universe. So:

  1. BASE settings are family-adaptive — a fast/technical signal (momentum, vol,
     liquidity) gets a higher base decay to keep turnover inside the gate;
     fundamental/style signals keep decay 0 (their proven high-Sharpe config, so
     no regression on what already works).
  2. When a candidate just MISSES a gate, `diagnose` names the settings-fixable
     problem (only NEAR-misses qualify — a hopeless alpha shouldn't burn a sim),
     and `retry_variant` returns ONE variant targeted at it:
        HIGH_TURNOVER    -> more decay (smooths the signal, cuts turnover)
        LOW_SHARPE/FIT   -> smaller universe TOP1000 (less noise -> higher Sharpe)
        HIGH_DRAWDOWN    -> lower truncation (less concentration)

Bounded on purpose: near-misses only, one retry each, capped per round — so the
round-time cost stays modest while still flipping the fixable near-passes.
"""
from __future__ import annotations

import re
from typing import Optional

from alpha_agent.brain.client import (
    DEFAULT_SETTINGS,
    MAX_DRAWDOWN,
    MAX_TURNOVER,
    MIN_FITNESS,
    MIN_SHARPE,
)

# An expression that looks "fast" (high-turnover-prone): momentum / volatility /
# liquidity legs built from price-volume fields.
_TECHNICAL_RE = re.compile(r"volume|ts_std_dev|ts_delta\(close|divide\(close, ts_mean")
# Options/IV fields — used to pin these signals to a coverage-dense universe.
_OPTIONS_RE = re.compile(r"implied_volatility|pcr_oi")
# Analyst estimate fields — sparse on TOP3000, pin to TOP1000.
_ANALYST_RE = re.compile(r"anl4_")

# Near-miss margins — beyond these a settings tweak won't realistically flip it,
# so it isn't worth a retry sim.
_TURNOVER_SLACK = 1.8   # turnover up to 1.8x the cap can often be decayed under it
_METRIC_FLOOR = 0.7     # sharpe/fitness at >=70% of the gate is a plausible flip
_DRAWDOWN_SLACK = 1.5


def base_settings_for(
    expr: str, *, fundamental_decay: int = 0, neutralization: str = "SUBINDUSTRY"
) -> dict:
    """Family-adaptive BASE settings. Fast/technical signals get a higher base
    decay (they're the high-turnover ones); fundamental/style signals keep the
    proven decay-0 config so nothing that already passes regresses."""
    decay = 12 if _TECHNICAL_RE.search(expr) else fundamental_decay
    settings = {**DEFAULT_SETTINGS, "decay": decay, "neutralization": neutralization}
    # Options/IV fields are dense only on liquid names; on TOP3000 they are
    # nan-sparse and the alpha degenerates (misses turnover/drawdown). Pin them
    # to TOP500 — the likely reason the highest-Sharpe family kept dying.
    if _OPTIONS_RE.search(expr):
        settings = {**settings, "universe": "TOP500"}
    elif _ANALYST_RE.search(expr):
        settings = {**settings, "universe": "TOP1000"}
    return settings


def _failed(metrics, name: str) -> bool:
    chk = (metrics.checks or {}).get(name) or {}
    return chk.get("result") == "FAIL"


def diagnose(metrics) -> Optional[str]:
    """The primary settings-fixable problem for a gate failure, or None when the
    failure isn't settings-addressable or is too far off to be worth a retry.
    Prefers BRAIN's own FAIL checks; falls back to raw-metric comparison."""
    to = metrics.turnover
    if (_failed(metrics, "HIGH_TURNOVER") or (to is not None and to > MAX_TURNOVER)) \
            and to is not None and to <= MAX_TURNOVER * _TURNOVER_SLACK:
        return "turnover"

    sh = metrics.sharpe
    if (_failed(metrics, "LOW_SHARPE") or (sh is not None and sh < MIN_SHARPE)) \
            and sh is not None and sh >= MIN_SHARPE * _METRIC_FLOOR:
        return "sharpe"

    fi = metrics.fitness
    if (_failed(metrics, "LOW_FITNESS") or (fi is not None and fi < MIN_FITNESS)) \
            and fi is not None and fi >= MIN_FITNESS * _METRIC_FLOOR:
        return "fitness"

    dd = metrics.drawdown
    if dd is not None and dd > MAX_DRAWDOWN and dd <= MAX_DRAWDOWN * _DRAWDOWN_SLACK:
        return "drawdown"

    return None


def retry_variant(base: dict, problem: Optional[str]) -> Optional[dict]:
    """A single settings variant targeted at the diagnosed problem (or None)."""
    if problem == "turnover":
        return {**base, "decay": min(int(base.get("decay", 0)) + 12, 32)}
    if problem in ("sharpe", "fitness"):
        return {**base, "universe": "TOP1000"}
    if problem == "drawdown":
        return {**base, "truncation": 0.04}
    return None
