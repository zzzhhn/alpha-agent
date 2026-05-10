# tests/fusion/test_normalize.py
import math
from alpha_agent.fusion.normalize import normalize_cross_section


def test_normalize_centers_and_scales():
    raw = {"A": 1.0, "B": 2.0, "C": 3.0, "D": 4.0, "E": 5.0}
    z = normalize_cross_section(raw)
    assert math.isclose(sum(z.values()), 0.0, abs_tol=1e-6)
    assert any(v > 0 for v in z.values()) and any(v < 0 for v in z.values())


def test_normalize_clips_at_3sigma():
    raw = {f"T{i}": 0.0 for i in range(20)}
    raw["TX"] = 100.0  # massive outlier
    z = normalize_cross_section(raw)
    assert z["TX"] == 3.0  # exactly clipped, not above


def test_normalize_handles_constant_universe():
    raw = {"A": 5.0, "B": 5.0, "C": 5.0}
    z = normalize_cross_section(raw)
    assert all(v == 0.0 for v in z.values())  # σ==0 → all 0


def test_normalize_skips_zero_confidence():
    """confidence=0 entries don't contribute to mean/sigma but get z=0 in output."""
    from alpha_agent.signals.base import SignalScore
    from datetime import datetime, UTC
    base = lambda t, raw, c: SignalScore(ticker=t, z=0.0, raw=raw, confidence=c,
                                          as_of=datetime.now(UTC), source="t", error=None)
    inputs = {"A": base("A", 1.0, 0.9), "B": base("B", 2.0, 0.9),
              "C": base("C", 99.0, 0.0)}
    z = normalize_cross_section(inputs, raw_field="raw")
    assert z["C"] == 0.0
    # only A,B contributed to mean → mean=1.5, sigma=0.5 → A=-1, B=+1
    assert math.isclose(z["A"], -1.0, abs_tol=1e-6)
    assert math.isclose(z["B"], 1.0, abs_tol=1e-6)
