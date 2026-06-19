"""Single data-only manifest for signal identity (roadmap step 3).

A signal's identity (weight, horizon, core-ness, cron cadence, IC tracking,
display label, fusion cap) used to be hand-maintained across ~10 independent
lists with no source of truth, so adding one signal meant ~10 coordinated edits
and a miss was a silent bug (weighted-but-never-computed, wrong-horizon label,
or a monitoring list that quietly drifted). This manifest is that source of
truth: every backend list is now a one-line derivation from SIGNAL_REGISTRY.

DATA-ONLY (council must-have): this module imports nothing heavy — no pandas,
no yfinance, no signal modules, no fusion / cron / api. Signal code is
referenced by STRING import path and resolved lazily by the consumer that
actually needs the module (the cron), never at registry import time. That keeps
the manifest safe to import on a serverless cold start and free of import-side-
effect coupling (a lazy-import regression test enforces this).

Signal implementation modules must NOT import this registry (no circular dep).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SignalMeta:
    """One signal's identity. Fields are split by meaning (not one vague
    `tier`) so each backend list derives from an explicit field."""

    name: str
    module_path: str       # e.g. "alpha_agent.signals.rsrs" (string, lazy-resolved)
    compute_fn: str        # base compute fn name; cron uses "a"+fn if async-native
    cron_group: str        # refresh cadence membership: "tech" | "mid" | "slow" | "full"
    core_for_coverage: bool  # in the sqrt-coverage core set?
    active_in_ic: bool     # tracked by the walk-forward IC engine?
    enabled_in_live: bool  # computed by the live crons?
    default_weight: float  # fusion weight (sums to 1.0 across the registry)
    horizon_days: int      # native forward horizon (trading days)
    fusion_cap: float | None  # STATIC_V2 guardrail cap (None = uncapped)
    label_zh: str
    label_en: str


# One row per signal. Order is the canonical signal order (matches the cron's
# historical _ALL_MODULES order). cron_group is the NON-full tier a signal
# refreshes in, or "full" when it is only refreshed by the full bootstrap.
SIGNAL_REGISTRY: tuple[SignalMeta, ...] = (
    SignalMeta("factor", "alpha_agent.signals.factor", "fetch_signal",
               "full", True, True, True, 0.30, 60, None, "因子", "Factor"),
    SignalMeta("technicals", "alpha_agent.signals.technicals", "fetch_signal",
               "tech", True, True, True, 0.15, 5, 0.10, "技术面", "Technicals"),
    SignalMeta("rsrs", "alpha_agent.signals.rsrs", "fetch_signal",
               "slow", False, True, True, 0.05, 20, None, "支阻强度", "RSRS"),
    SignalMeta("analyst", "alpha_agent.signals.analyst", "fetch_signal",
               "mid", True, True, True, 0.10, 20, None, "分析师", "Analyst"),
    SignalMeta("earnings", "alpha_agent.signals.earnings", "fetch_signal",
               "full", True, True, True, 0.10, 20, None, "财报", "Earnings"),
    SignalMeta("news", "alpha_agent.signals.news", "fetch_signal",
               "slow", True, True, True, 0.10, 3, None, "新闻", "News"),
    SignalMeta("insider", "alpha_agent.signals.insider", "fetch_signal",
               "slow", False, True, True, 0.05, 20, None, "内部交易", "Insider"),
    SignalMeta("options", "alpha_agent.signals.options", "fetch_signal",
               "mid", False, True, True, 0.05, 5, None, "期权", "Options"),
    SignalMeta("premarket", "alpha_agent.signals.premarket", "fetch_signal",
               "mid", False, True, True, 0.05, 1, None, "盘前", "Pre-market"),
    SignalMeta("macro", "alpha_agent.signals.macro", "fetch_signal",
               "full", True, True, True, 0.05, 20, None, "宏观 (波动率)", "Macro (Vol)"),
    SignalMeta("calendar", "alpha_agent.signals.calendar", "fetch_signal",
               "full", False, True, True, 0.00, 5, None, "日历", "Calendar"),
    SignalMeta("political_impact", "alpha_agent.signals.political_impact", "fetch_signal",
               "full", False, True, True, 0.00, 5, None, "政治", "Political"),
    # geopolitical_impact: split from political_impact (A3), display-only weight
    # 0, and not yet IC-tracked (active_in_ic=False) until it accrues history.
    SignalMeta("geopolitical_impact", "alpha_agent.signals.geopolitical_impact",
               "fetch_signal", "full", False, False, True, 0.00, 5, None,
               "地缘 (关税/Fed)", "Geopolitical"),
    SignalMeta("supply_chain", "alpha_agent.signals.supply_chain", "fetch_signal",
               "slow", False, True, True, 0.05, 60, None, "供应链卡点", "Supply-Chain"),
)

# The non-full cron tiers, in fast_intraday's historical cadence grouping.
_CADENCE_TIERS = ("tech", "mid", "slow")


# --- derivations (every backend list comes from here) ---

def default_weights() -> dict[str, float]:
    """name -> fusion weight (was fusion/weights.DEFAULT_WEIGHTS)."""
    return {s.name: s.default_weight for s in SIGNAL_REGISTRY}


def signal_horizon_days() -> dict[str, int]:
    """name -> native forward horizon (was signals/horizons.SIGNAL_HORIZON_DAYS)."""
    return {s.name: s.horizon_days for s in SIGNAL_REGISTRY}


def core_signals() -> tuple[str, ...]:
    """The sqrt-coverage core set (was fusion/policy._CORE_SIGNALS)."""
    return tuple(s.name for s in SIGNAL_REGISTRY if s.core_for_coverage)


def fusion_caps() -> dict[str, float]:
    """name -> guardrail cap for the capped signals (was the STATIC_V2 caps)."""
    return {s.name: s.fusion_cap for s in SIGNAL_REGISTRY if s.fusion_cap is not None}


def active_ic_signals() -> tuple[str, ...]:
    """Signals tracked by the IC engine (was ic_engine._ACTIVE_SIGNALS)."""
    return tuple(s.name for s in SIGNAL_REGISTRY if s.active_in_ic)


def all_signal_names() -> list[str]:
    """Every signal, canonical order (was the hand-kept _SIGNAL_NAMES lists)."""
    return [s.name for s in SIGNAL_REGISTRY]


def cron_tiers() -> dict[str, list[str]]:
    """tier -> signal names refreshed at that cadence (was fast_intraday._TIERS).
    full = every signal; the cadence tiers are membership by cron_group."""
    tiers: dict[str, list[str]] = {
        t: [s.name for s in SIGNAL_REGISTRY if s.cron_group == t]
        for t in _CADENCE_TIERS
    }
    tiers["full"] = [s.name for s in SIGNAL_REGISTRY]
    return tiers


def signal_labels() -> dict[str, dict[str, str]]:
    """name -> {zh, en} display labels (was the frontend signal-labels mirror)."""
    return {s.name: {"zh": s.label_zh, "en": s.label_en} for s in SIGNAL_REGISTRY}


def fixture_z_map() -> dict[str, float]:
    """Deterministic per-signal z used by the build_card CLI fixture (never
    affects production ratings). z==0.0 marks a signal the fixture treats as
    absent (confidence 0 -> dropped by combine): the display-only signals
    (calendar / political / geopolitical) and supply_chain (sparse). Was the
    hand-kept _z_map in cli/build_card."""
    return {s.name: _FIXTURE_Z[s.name] for s in SIGNAL_REGISTRY}


# Fixed demo z-values (CLI fixture only). Every registry signal has an entry.
_FIXTURE_Z = {
    "factor": 1.5, "technicals": 0.8, "rsrs": 0.7, "analyst": 1.2,
    "earnings": 0.6, "news": 0.3, "insider": 0.9, "options": 0.4,
    "premarket": 0.7, "macro": 0.2, "calendar": 0.0, "political_impact": 0.0,
    "geopolitical_impact": 0.0, "supply_chain": 0.0,
}


def module_path(name: str) -> str:
    return _BY_NAME[name].module_path


_BY_NAME: dict[str, SignalMeta] = {s.name: s for s in SIGNAL_REGISTRY}
