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
