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
    # NOTE: an options->TOP500 pin was REVERTED — the DB proved the opposite: the
    # proven high-Sharpe options factors (S=1.6-2.5) all ran on TOP3000/TOP1000, and
    # TOP500 dropped them to ~0. Options now use the default TOP3000. Analyst
    # estimates ARE sparse, so they still pin to TOP1000.
    if _ANALYST_RE.search(expr):
        settings = {**settings, "universe": "TOP1000"}
    return settings


def _failed(metrics, name: str) -> bool:
    chk = (metrics.checks or {}).get(name) or {}
    return chk.get("result") == "FAIL"


# Settings-EXPLORATION families: the frontier/catalog mechanisms whose configs
# are unproven. value/options/other keep their DB-proven TOP3000/delay-1/
# SUBINDUSTRY untouched (the blanket TOP500 options pin that tanked a proven
# Sharpe 2.5 alpha is the cautionary tale: explore on NEW mechanisms, never
# re-pin proven ones).
_EXPLORE_FAMILIES = frozenset({
    "microstructure", "seasonality", "overnight", "iv_term", "vrp", "quality",
    "score", "sentiment", "lowvol", "momentum", "revision",
})
# Fast signals decay hardest by t+1 — the only families worth a delay-0 probe
# (BRAIN's own D0 checks apply their D0 bars; the verdict stays authoritative).
_DELAY0_FAMILIES = frozenset({"microstructure", "overnight"})


def vary_settings(base: dict, family: str, rng) -> dict:
    """Per-candidate settings exploration for unproven mechanisms. 2026-07-11
    audit: 255 sims over 3 days ran 100% delay-1, 100% SUBINDUSTRY, 86% TOP3000
    — three of four settings axes frozen, while community evidence shows the
    SAME expression re-rates materially across universe/neutralization/decay
    (documented triple-pass of one expression on three configs). Default-heavy
    priors so most sims still run the base config; the exploration tail buys
    information, not a regime change."""
    if family not in _EXPLORE_FAMILIES:
        return base
    s = dict(base)
    r = rng.random()
    if r < 0.15:
        s["universe"] = "TOP500"
    elif r < 0.40:
        s["universe"] = "TOP1000"
    r = rng.random()
    if r < 0.20:
        s["neutralization"] = "INDUSTRY"
    elif r < 0.30:
        s["neutralization"] = "MARKET"
    if family in _DELAY0_FAMILIES and rng.random() < 0.15:
        s["delay"] = 0
    if rng.random() < 0.45:
        s["decay"] = min(int(s.get("decay", 0)) + rng.choice((4, 8, 16)), 40)
    return s


def diagnose(metrics) -> Optional[str]:
    """The primary settings-fixable problem for a gate failure, or None when the
    failure isn't settings-addressable or is too far off to be worth a retry.
    Prefers BRAIN's own FAIL checks; falls back to raw-metric comparison."""
    to = metrics.turnover
    if (_failed(metrics, "HIGH_TURNOVER") or (to is not None and to > MAX_TURNOVER)) \
            and to is not None and to <= MAX_TURNOVER * _TURNOVER_SLACK:
        return "turnover"

    sh = metrics.sharpe
    fi = metrics.fitness
    # Sharpe-strong / Fitness-weak (e.g. vol_shock 2026-07-11: S=1.40, F=0.70,
    # T=0.32): Fitness = Sharpe*sqrt(|returns|/max(turnover, 0.125)), so cutting
    # turnover via decay lifts Fitness by sqrt(T/0.125) at Sharpe held. Eligible
    # when that ceiling clears the bar — a PHYSICS test, not the generic 70%
    # floor (which wrongly excluded F=0.70).
    to_ = metrics.turnover
    if (sh is not None and sh >= MIN_SHARPE
            and (_failed(metrics, "LOW_FITNESS") or (fi is not None and fi < MIN_FITNESS))
            and fi is not None and fi > 0 and to_ is not None and to_ > 0.125):
        potential = fi * (to_ / 0.125) ** 0.5
        if potential >= MIN_FITNESS:
            return "fitness_turnover"

    if (_failed(metrics, "LOW_SHARPE") or (sh is not None and sh < MIN_SHARPE)) \
            and sh is not None and sh >= MIN_SHARPE * _METRIC_FLOOR:
        return "sharpe"

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
    if problem == "fitness_turnover":
        # Aggressive smoothing: halve-ish the turnover so Fitness gains ~sqrt(2)x
        # while the (already-clearing) Sharpe absorbs the small decay drag.
        return {**base, "decay": min(int(base.get("decay", 0)) + 16, 40)}
    if problem in ("sharpe", "fitness"):
        return {**base, "universe": "TOP1000"}
    if problem == "drawdown":
        return {**base, "truncation": 0.04}
    return None
