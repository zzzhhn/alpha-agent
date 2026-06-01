# tests/signals/test_earnings.py
from datetime import UTC, date, datetime, timedelta

from alpha_agent.signals.earnings import fetch_signal, prime_cache

_AS_OF = datetime(2026, 6, 1, tzinfo=UTC)


def _row(surprise, sigma=0.05, days_ago=3, **extra):
    r = {
        "recent_surprise": surprise,
        "sigma": sigma,
        "report_date": (
            (_AS_OF.date() - timedelta(days=days_ago)) if days_ago is not None else None
        ),
        "next_date": None,
        "eps_estimate": None,
        "revenue_estimate": None,
    }
    r.update(extra)
    return r


def test_recent_beat_positive_z():
    prime_cache({"AAPL": _row(0.10)})  # +0.10 / 0.05 sigma, 3d ago
    out = fetch_signal("AAPL", _AS_OF)
    assert out["z"] > 0
    assert out["raw"]["surprise_pct"] == 10.0


def test_recent_miss_negative_z():
    prime_cache({"AAPL": _row(-0.10)})
    assert fetch_signal("AAPL", _AS_OF)["z"] < 0


def test_old_report_decays_toward_zero():
    prime_cache({"X": _row(0.20, days_ago=3), "Y": _row(0.20, days_ago=90)})
    assert fetch_signal("X", _AS_OF)["z"] > fetch_signal("Y", _AS_OF)["z"]
    assert abs(fetch_signal("Y", _AS_OF)["z"]) < 0.05  # exp(-90/14) crushes it


def test_no_entry_is_no_signal():
    prime_cache({"AAPL": _row(0.10)})
    out = fetch_signal("ZZZ", _AS_OF)
    assert out["z"] is None
    assert out["confidence"] == 0.0
    assert out["error"] == "no earnings data"


def test_upcoming_only_is_no_signal_but_keeps_card():
    prime_cache({
        "AAPL": {
            "recent_surprise": None, "sigma": None, "report_date": None,
            "next_date": date(2026, 7, 30), "eps_estimate": 1.5,
            "revenue_estimate": 1.0e11,
        }
    })
    out = fetch_signal("AAPL", _AS_OF)
    assert out["z"] is None  # no gradeable surprise -> "—"
    assert out["raw"]["next_date"] == "2026-07-30"  # card still populated
    assert out["raw"]["eps_estimate"] == 1.5
