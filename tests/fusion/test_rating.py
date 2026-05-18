# tests/fusion/test_rating.py
from alpha_agent.fusion.rating import map_to_tier, compute_confidence


def test_tier_boundaries():
    assert map_to_tier(2.0) == "BUY"
    assert map_to_tier(1.5001) == "BUY"
    assert map_to_tier(1.4999) == "OW"
    assert map_to_tier(0.5001) == "OW"
    assert map_to_tier(0.4999) == "HOLD"
    assert map_to_tier(0.0) == "HOLD"
    assert map_to_tier(-0.5) == "HOLD"
    assert map_to_tier(-0.5001) == "UW"
    assert map_to_tier(-1.5) == "UW"
    assert map_to_tier(-1.5001) == "SELL"


def test_confidence_high_when_aligned():
    zs = [1.5, 1.4, 1.6, 1.5, 1.4]
    assert compute_confidence(zs) > 0.85


def test_confidence_low_on_disagreement():
    zs = [3.0, -3.0, 0.0, 2.0, -2.0]
    assert compute_confidence(zs) < 0.30


def test_confidence_empty_returns_zero():
    assert compute_confidence([]) == 0.0


# --- B2 no-trade band (2026-05-19) ------------------------------------

from alpha_agent.fusion.rating import map_to_tier_with_band


def test_band_keeps_prev_tier_within_hysteresis():
    """Threshold-adjacent wobble that would otherwise flip OW->HOLD every
    cron tick stays sticky inside the ±0.15z band."""
    # Yesterday's tier = OW (composite was, say, 0.7). Today composite
    # drifts to 0.45 — under legacy map_to_tier this is HOLD. With band,
    # OW extends down to 0.5 - 0.15 = 0.35, so 0.45 stays OW.
    assert map_to_tier_with_band(0.45, "OW", band=0.15) == "OW"
    # Symmetric case crossing HOLD<->UW
    assert map_to_tier_with_band(-0.4, "HOLD", band=0.15) == "HOLD"


def test_band_releases_when_composite_clears_band_edge():
    """Once composite clearly exits the band, tier follows. Band is
    symmetric on both sides — OW extends to (0.35, 1.65), so 0.34 yields
    to HOLD downward and 1.66 yields to BUY upward, but 1.6 stays OW."""
    assert map_to_tier_with_band(0.34, "OW", band=0.15) == "HOLD"
    assert map_to_tier_with_band(1.66, "OW", band=0.15) == "BUY"
    # Stickiness on the upside: 1.6 still inside (0.35, 1.65), keeps OW
    assert map_to_tier_with_band(1.6, "OW", band=0.15) == "OW"


def test_band_zero_or_none_prev_falls_through():
    """band=0 disables hysteresis; prev_tier=None means cold start."""
    assert map_to_tier_with_band(0.45, "OW", band=0.0) == "HOLD"
    assert map_to_tier_with_band(0.45, None, band=0.15) == "HOLD"


def test_band_handles_unknown_prev_tier():
    """If prev_tier is a stale or unexpected string (legacy data), don't
    crash — fall through to legacy map_to_tier."""
    assert map_to_tier_with_band(0.45, "STRONG_BUY", band=0.15) == "HOLD"


def test_band_env_var_default():
    """Without ALPHA_TIER_BAND_Z set, the band defaults to 0.15."""
    import os
    saved = os.environ.pop("ALPHA_TIER_BAND_Z", None)
    try:
        # 0.45 should be HOLD without band, OW with default 0.15 if prev=OW
        assert map_to_tier_with_band(0.45, "OW") == "OW"
    finally:
        if saved is not None:
            os.environ["ALPHA_TIER_BAND_Z"] = saved


def test_band_env_var_override(monkeypatch):
    """ALPHA_TIER_BAND_Z overrides the default."""
    monkeypatch.setenv("ALPHA_TIER_BAND_Z", "0.3")
    # band=0.3 means OW extends to 0.5-0.3=0.2; 0.3 stays OW
    assert map_to_tier_with_band(0.3, "OW") == "OW"
    # 0.19 clears the band, falls back to HOLD
    assert map_to_tier_with_band(0.19, "OW") == "HOLD"


def test_band_rejects_absurd_env_values(monkeypatch):
    """Negative or >0.5 band collapses entire tier transitions; reject."""
    monkeypatch.setenv("ALPHA_TIER_BAND_Z", "-0.5")
    assert map_to_tier_with_band(0.45, "OW") == "OW"  # falls back to 0.15
    monkeypatch.setenv("ALPHA_TIER_BAND_Z", "999")
    assert map_to_tier_with_band(0.45, "OW") == "OW"  # falls back to 0.15
    monkeypatch.setenv("ALPHA_TIER_BAND_Z", "not_a_float")
    assert map_to_tier_with_band(0.45, "OW") == "OW"  # falls back to 0.15
