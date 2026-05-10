# tests/fusion/test_combine.py
from datetime import datetime, UTC
from alpha_agent.signals.base import SignalScore
from alpha_agent.fusion.combine import combine


def _sig(name: str, z: float, conf: float = 0.9) -> SignalScore:
    return SignalScore(ticker="AAPL", z=z, raw=z, confidence=conf,
                       as_of=datetime.now(UTC), source=name, error=None)


def test_combine_weighted_sum():
    signals = {"factor": _sig("factor", 1.0), "technicals": _sig("technicals", 1.0)}
    weights = {"factor": 0.6, "technicals": 0.4}
    result = combine(signals, weights)
    assert abs(result.composite - 1.0) < 1e-9
    assert len(result.breakdown) == 2


def test_combine_redistributes_zero_confidence():
    signals = {"factor": _sig("factor", 1.0, 0.9),
               "macro": _sig("macro", 99.0, 0.0)}
    weights = {"factor": 0.50, "macro": 0.50}
    result = combine(signals, weights)
    # macro confidence=0 → effective weight 0; factor takes full
    assert abs(result.composite - 1.0) < 1e-9
    macro_entry = next(b for b in result.breakdown if b["signal"] == "macro")
    assert macro_entry["weight"] == 0.5  # original weight retained for display
    assert macro_entry["contribution"] == 0.0  # but no contribution


def test_combine_calendar_excluded():
    """calendar weight=0 → never enters composite even with non-zero z."""
    signals = {"factor": _sig("factor", 1.0), "calendar": _sig("calendar", 5.0)}
    from alpha_agent.fusion.weights import DEFAULT_WEIGHTS
    result = combine(signals, DEFAULT_WEIGHTS)
    assert all(b["signal"] != "calendar" or b["contribution"] == 0
               for b in result.breakdown)


def test_combine_drops_nan_z_signal_doesnt_poison_composite():
    """A signal with confidence > 0 but z=NaN must NOT poison composite."""
    from datetime import datetime, UTC
    import math
    from alpha_agent.signals.base import SignalScore
    from alpha_agent.fusion.combine import combine

    nan_sig = SignalScore(
        ticker="AAPL", z=float("nan"), raw=None, confidence=0.9,
        as_of=datetime.now(UTC), source="test", error=None,
    )
    good_sig = SignalScore(
        ticker="AAPL", z=1.0, raw=1.0, confidence=0.9,
        as_of=datetime.now(UTC), source="test", error=None,
    )
    signals = {"factor": nan_sig, "technicals": good_sig}
    weights = {"factor": 0.30, "technicals": 0.20}
    result = combine(signals, weights)
    # Composite must be finite, never NaN
    assert math.isfinite(result.composite), f"composite leaked NaN: {result.composite}"
    # Drops factor (z=NaN) → all weight redistributes to technicals
    assert abs(result.composite - 1.0) < 1e-9
    # NaN-z signal preserved in breakdown but with weight_effective=0 + contribution=0
    factor_entry = next(b for b in result.breakdown if b["signal"] == "factor")
    assert factor_entry["weight_effective"] == 0
    assert factor_entry["contribution"] == 0.0
