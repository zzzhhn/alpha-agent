# tests/signals/test_insider.py
from datetime import UTC, datetime

from alpha_agent.signals import insider
from alpha_agent.signals.insider import fetch_signal, prime_cache

_AS_OF = datetime(2026, 6, 1, tzinfo=UTC)


def test_primed_net_buying_yields_positive_z():
    prime_cache({"AAPL": (2_000_000.0, 3)})
    out = fetch_signal("AAPL", _AS_OF)
    assert out["z"] > 0
    assert out["raw"]["net_value"] == 2_000_000.0
    assert out["confidence"] == 0.70


def test_primed_net_selling_yields_negative_z():
    prime_cache({"AAPL": (-2_000_000.0, 3)})
    assert fetch_signal("AAPL", _AS_OF)["z"] < 0


def test_ticker_absent_from_cache_has_no_signal():
    prime_cache({"AAPL": (2_000_000.0, 3)})
    out = fetch_signal("XYZ", _AS_OF)  # not primed
    # z=None -> dropped from composite + excluded from the dimension grade
    # (shown "—"), not a misleading neutral 0.
    assert out["z"] is None
    assert out["confidence"] == 0.0
    assert out["error"] == "no filings in 30d"


def test_zero_filings_has_no_signal():
    prime_cache({"XYZ": (0.0, 0)})
    out = fetch_signal("XYZ", _AS_OF)
    assert out["z"] is None
    assert out["confidence"] == 0.0


def test_prime_cache_replaces_not_merges():
    prime_cache({"AAPL": (1.0, 1)})
    prime_cache({"MSFT": (1.0, 1)})
    assert insider._NET_CACHE == {"MSFT": (1.0, 1)}
