# tests/fusion/test_coverage.py
"""Coverage-aware fusion + weight policy (council 2026-06-17 items #1 + #2)."""
import math
from datetime import UTC, datetime

from alpha_agent.fusion.combine import combine
from alpha_agent.fusion.policy import get_active_policy

_NOW = datetime.now(UTC)


def _sc(z: float, conf: float = 0.8) -> dict:
    return {
        "ticker": "X", "z": z, "raw": None, "confidence": conf,
        "as_of": _NOW, "source": "t", "error": None,
    }


def _full_sigs() -> dict:
    names = [
        "factor", "technicals", "analyst", "earnings", "news", "macro",
        "insider", "options", "premarket", "supply_chain",
    ]
    return {n: _sc(1.0) for n in names}


def test_active_policy_is_static_v2_with_expected_core():
    p = get_active_policy()
    assert p.policy_id == "static_v2_technicals_guardrail"
    assert p.mode == "static"
    assert p.horizon == "5d"
    assert p.missing_policy == "coverage_sqrt"
    assert p.core_set() == {
        "factor", "technicals", "analyst", "earnings", "news", "macro",
    }


def test_no_coverage_core_is_legacy_behavior():
    w = get_active_policy().weights
    sigs = _full_sigs()
    legacy = combine(sigs, w)
    assert legacy.coverage is None
    assert combine(sigs, w, coverage_core=None).composite == legacy.composite


def test_full_core_coverage_leaves_composite_unchanged():
    p = get_active_policy()
    sigs = _full_sigs()
    legacy = combine(sigs, p.weights).composite
    r = combine(sigs, p.weights, coverage_core=p.core_set())
    assert abs(r.coverage - 1.0) < 1e-12
    assert abs(r.composite - legacy) < 1e-12


def test_missing_core_signal_damps_composite_by_sqrt_coverage():
    p = get_active_policy()
    sigs = _full_sigs()
    sigs["factor"] = _sc(1.0, conf=0.0)  # factor dropped (no data)
    legacy = combine(sigs, p.weights).composite  # renormalized, no damping
    r = combine(sigs, p.weights, coverage_core=p.core_set())
    # core total weight = factor.30+tech.20+analyst.10+earnings.10+news.10+macro.05 = 0.85
    expected_cov = (0.85 - 0.30) / 0.85
    assert abs(r.coverage - expected_cov) < 1e-9
    assert abs(r.composite - legacy * math.sqrt(expected_cov)) < 1e-9


def test_missing_sparse_signal_does_not_penalize_coverage():
    p = get_active_policy()
    sigs = _full_sigs()
    sigs["insider"] = _sc(1.0, conf=0.0)  # sparse, not in core
    r = combine(sigs, p.weights, coverage_core=p.core_set())
    assert abs(r.coverage - 1.0) < 1e-12


def _contrib(res, sig):
    return next(b["contribution"] for b in res.breakdown if b["signal"] == sig)


def test_active_policy_caps_technicals():
    # council #5: the live policy guardrails technicals.
    p = get_active_policy()
    assert p.caps_dict().get("technicals") == 0.10


def test_cap_reduces_signal_without_reallocating():
    p = get_active_policy()
    sigs = _full_sigs()
    uncapped = combine(sigs, p.weights, coverage_core=p.core_set())
    capped = combine(
        sigs, p.weights, coverage_core=p.core_set(), caps={"technicals": 0.10},
    )
    # technicals contribution shrinks (weight scaled 0.10/0.20 = 0.5)...
    assert abs(_contrib(capped, "technicals")) < abs(_contrib(uncapped, "technicals"))
    # ...a non-capped signal's contribution is UNCHANGED (no reallocation)...
    assert abs(_contrib(capped, "factor") - _contrib(uncapped, "factor")) < 1e-12
    # ...so the composite is smaller (freed weight went to neutral, not others).
    assert capped.composite < uncapped.composite


def test_no_caps_is_identical():
    p = get_active_policy()
    sigs = _full_sigs()
    a = combine(sigs, p.weights, coverage_core=p.core_set(), caps=None)
    b = combine(sigs, p.weights, coverage_core=p.core_set(), caps={})
    assert a.composite == b.composite
