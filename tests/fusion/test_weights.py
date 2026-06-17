# tests/fusion/test_weights.py
from alpha_agent.fusion.weights import DEFAULT_WEIGHTS, normalize_weights


def test_default_weights_form_a_valid_distribution():
    # The validated base signals sum to 1.0. Display-only signals (calendar /
    # political_impact / geopolitical_impact, weight 0) and the serenity
    # supply_chain exploratory tilt (0.05) sit on top, so the raw sum is >1.0
    # by design; the fusion path renormalizes, so the absolute sum need not be
    # 1.0 (council 2026-06-17 coverage-aware fusion formalizes this).
    extra = {"calendar", "political_impact", "geopolitical_impact", "supply_chain"}
    base = sum(w for k, w in DEFAULT_WEIGHTS.items() if k not in extra)
    assert abs(base - 1.0) < 1e-9
    # The real fusion contract: normalized weights always sum to 1.0.
    assert abs(sum(normalize_weights(DEFAULT_WEIGHTS).values()) - 1.0) < 1e-9


def test_normalize_redistributes_when_some_dropped():
    base = {"factor": 0.30, "technicals": 0.20, "macro": 0.05}
    out = normalize_weights(base, drop={"macro"})
    assert "macro" not in out
    assert abs(sum(out.values()) - 1.0) < 1e-9
    # factor : technicals ratio preserved
    assert abs(out["factor"] / out["technicals"] - 1.5) < 1e-9


def test_normalize_returns_zero_dict_when_all_dropped():
    out = normalize_weights({"factor": 1.0}, drop={"factor"})
    assert out == {}
