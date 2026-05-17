# tests/fusion/test_weights.py
from alpha_agent.fusion.weights import DEFAULT_WEIGHTS, normalize_weights


def test_default_weights_sum_to_one_excluding_calendar():
    s = sum(w for k, w in DEFAULT_WEIGHTS.items() if k != "calendar")
    assert abs(s - 1.0) < 1e-9


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
