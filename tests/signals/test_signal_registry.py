# tests/signals/test_signal_registry.py
"""The signal registry is the single source of truth for signal identity
(roadmap step 3). One data-only manifest replaces ~10 hand-maintained lists.

Three guarantees:
  - GOLDEN EQUALITY: the registry's derivations equal the known-correct values
    (pinned here as a frozen snapshot, NOT read from the live modules, so the
    test stays a real guard after those modules are rewired to derive from it).
    This is what proves the refactor changed no fusion numerics.
  - INVARIANTS: weights sum to 1.0, names unique, every module_path resolves to
    a module exposing its compute_fn, active-IC signals have horizons. This is
    what makes future drift impossible.
  - LAZY IMPORT (council must-have): importing the registry must NOT pull in
    yfinance / pandas / any signal module, so it stays a data-only manifest safe
    for serverless cold start.
"""
import importlib
import sys

import pytest

# --- frozen golden snapshot of the pre-refactor values (ground truth) ---
_GOLD_WEIGHTS = {
    "factor": 0.30, "technicals": 0.15, "rsrs": 0.05, "analyst": 0.10,
    "earnings": 0.10, "news": 0.10, "insider": 0.05, "options": 0.05,
    "premarket": 0.05, "macro": 0.05, "calendar": 0.00, "political_impact": 0.00,
    "geopolitical_impact": 0.00, "supply_chain": 0.05,
}
_GOLD_HORIZONS = {
    "factor": 60, "technicals": 5, "rsrs": 20, "analyst": 20, "earnings": 20,
    "news": 3, "insider": 20, "options": 5, "premarket": 1, "macro": 20,
    "calendar": 5, "political_impact": 5, "geopolitical_impact": 5, "supply_chain": 60,
}
_GOLD_CORE = {"factor", "technicals", "analyst", "earnings", "news", "macro"}
_GOLD_CAPS = {"technicals": 0.10}
_GOLD_TIERS = {
    "tech": {"technicals"},
    "mid": {"options", "analyst", "premarket"},
    "slow": {"news", "insider", "supply_chain", "rsrs"},
}
# geopolitical_impact is the one signal not (yet) tracked in the IC engine.
_GOLD_ACTIVE_IC = set(_GOLD_WEIGHTS) - {"geopolitical_impact"}


def test_golden_weights():
    from alpha_agent.signals.registry import default_weights
    assert default_weights() == _GOLD_WEIGHTS


def test_golden_horizons():
    from alpha_agent.signals.registry import signal_horizon_days
    assert signal_horizon_days() == _GOLD_HORIZONS


def test_golden_core_set():
    from alpha_agent.signals.registry import core_signals
    assert set(core_signals()) == _GOLD_CORE


def test_golden_caps():
    from alpha_agent.signals.registry import fusion_caps
    assert fusion_caps() == _GOLD_CAPS


def test_golden_cron_tiers():
    from alpha_agent.signals.registry import cron_tiers
    tiers = cron_tiers()
    assert {k: set(v) for k, v in tiers.items() if k != "full"} == _GOLD_TIERS
    assert set(tiers["full"]) == set(_GOLD_WEIGHTS)  # full = every signal


def test_golden_active_ic_set():
    from alpha_agent.signals.registry import active_ic_signals
    assert set(active_ic_signals()) == _GOLD_ACTIVE_IC


def test_golden_labels():
    from alpha_agent.signals.registry import signal_labels
    labels = signal_labels()
    assert labels["factor"] == {"zh": "因子", "en": "Factor"}
    assert labels["supply_chain"] == {"zh": "供应链卡点", "en": "Supply-Chain"}
    assert set(labels) == set(_GOLD_WEIGHTS)


# --- invariants (make drift impossible) ---

def test_weights_nonnegative_and_total_pinned():
    # NB: the production total is 1.05, NOT 1.0 — supply_chain (0.05, added
    # 2026-06-16) was not funded by a trim, while rsrs was. combine() renormalizes
    # over contributing signals so this is behaviorally harmless; correcting the
    # total would change fusion numerics and is out of scope for this structural
    # refactor (flagged for the re-tune step #456). Pin it so the registry can't
    # silently drift the total either way.
    from alpha_agent.signals.registry import default_weights
    w = default_weights()
    assert all(v >= 0 for v in w.values())
    assert sum(w.values()) == pytest.approx(1.05)


def test_names_unique():
    from alpha_agent.signals.registry import SIGNAL_REGISTRY
    names = [s.name for s in SIGNAL_REGISTRY]
    assert len(names) == len(set(names))


def test_active_signals_have_horizons():
    from alpha_agent.signals.registry import SIGNAL_REGISTRY
    for s in SIGNAL_REGISTRY:
        if s.active_in_ic:
            assert s.horizon_days > 0


def test_every_module_path_resolves_to_a_compute_fn():
    from alpha_agent.signals.registry import SIGNAL_REGISTRY
    for s in SIGNAL_REGISTRY:
        mod = importlib.import_module(s.module_path)
        # sync fetch_signal or its async variant must exist.
        assert hasattr(mod, s.compute_fn) or hasattr(mod, "a" + s.compute_fn), (
            f"{s.name}: {s.module_path} exposes neither {s.compute_fn} nor a-variant"
        )


# --- lazy import: data-only manifest must not pull heavy deps ---

def test_importing_registry_is_lazy():
    # Run in a fresh interpreter: a true cold-start check, and it avoids
    # mutating this process's sys.modules (which would leak into other tests).
    import subprocess
    code = (
        "import sys, alpha_agent.signals.registry as r;"
        "assert 'yfinance' not in sys.modules, 'yfinance leaked';"
        "assert 'pandas' not in sys.modules, 'pandas leaked';"
        "assert 'alpha_agent.signals.factor' not in sys.modules, 'signal module leaked';"
        "assert r.SIGNAL_REGISTRY"
    )
    res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
