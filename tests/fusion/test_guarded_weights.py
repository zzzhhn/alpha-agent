# tests/fusion/test_guarded_weights.py
"""Guarded activation of the adaptive weights (roadmap step 5).

The adaptive EWMA-ICIR subsystem writes signal_weight_current but nothing live
consumed it (inert = false capability, forbidden by the council). Guarded
activation closes the loop SAFELY: effective = (1-a)*static + a*adaptive with
a small a (0.10), and hard fallbacks — any signal lacking adaptive evidence OR
failing the min-sample gate stays at its static prior, clamped non-negative.
So with no adaptive rows the effective weights equal the static ones exactly.
"""
import pytest

from alpha_agent.fusion.guarded_weights import (
    GUARDED_ALPHA,
    blend_guarded,
    eligible_signals,
    get_effective_weights,
)
from alpha_agent.storage.postgres import close_pool, get_pool


# --- pure blend logic ---

def test_no_adaptive_returns_static_exactly():
    static = {"factor": 0.30, "technicals": 0.15, "macro": 0.05}
    assert blend_guarded(static, {}, eligible=set()) == static


def test_eligible_signal_is_pulled_toward_adaptive():
    static = {"factor": 0.30}
    adaptive = {"factor": 0.50}
    out = blend_guarded(static, adaptive, eligible={"factor"}, alpha=0.10)
    # 0.9*0.30 + 0.1*0.50 = 0.32
    assert out["factor"] == pytest.approx(0.32)


def test_adaptive_present_but_not_eligible_falls_back_to_static():
    static = {"factor": 0.30}
    adaptive = {"factor": 0.50}
    out = blend_guarded(static, adaptive, eligible=set(), alpha=0.10)
    assert out["factor"] == pytest.approx(0.30)  # min-sample gate not met


def test_blend_is_clamped_nonnegative():
    static = {"x": 0.05}
    adaptive = {"x": -1.0}  # pathological negative evidence
    out = blend_guarded(static, adaptive, eligible={"x"}, alpha=0.10)
    assert out["x"] >= 0.0


def test_default_alpha_is_small():
    assert 0.0 < GUARDED_ALPHA <= 0.10


# --- DB integration ---

@pytest.fixture
async def pool(applied_db):
    p = await get_pool(applied_db)
    yield p
    await close_pool()


async def _seed_adaptive(pool, weights):
    for sig, w in weights.items():
        await pool.execute(
            "INSERT INTO signal_weight_current (signal_name, status, weight, last_updated) "
            "VALUES ($1, 'live', $2, now())",
            sig, w,
        )


async def _seed_ic_history(pool, sig, n):
    from datetime import UTC, datetime, timedelta
    base = datetime(2026, 6, 1, tzinfo=UTC)
    for i in range(n):
        await pool.execute(
            "INSERT INTO signal_ic_history "
            "(signal_name, window_days, horizon_days, computed_at, ic, n_observations) "
            "VALUES ($1, 30, 5, $2, 0.05, 50)",
            sig, base + timedelta(days=i),
        )


@pytest.mark.asyncio
async def test_get_effective_weights_no_adaptive_is_pure_static(pool):
    static = {"factor": 0.30, "macro": 0.05}
    eff = await get_effective_weights(pool, static=static, persist=False)
    assert eff == static


@pytest.mark.asyncio
async def test_eligible_signals_respects_min_obs(pool):
    await _seed_ic_history(pool, "factor", 12)   # >= min_obs
    await _seed_ic_history(pool, "macro", 3)      # < min_obs
    elig = await eligible_signals(pool, min_obs=10)
    assert "factor" in elig
    assert "macro" not in elig


@pytest.mark.asyncio
async def test_get_effective_weights_blends_only_eligible_and_persists(pool):
    static = {"factor": 0.30, "macro": 0.05}
    await _seed_adaptive(pool, {"factor": 0.50, "macro": 0.50})
    await _seed_ic_history(pool, "factor", 12)   # eligible
    await _seed_ic_history(pool, "macro", 2)      # ineligible -> stays static
    eff = await get_effective_weights(pool, static=static, alpha=0.10, persist=True)
    assert eff["factor"] == pytest.approx(0.32)   # blended
    assert eff["macro"] == pytest.approx(0.05)    # fallback (min-sample)

    # persisted as status='effective' for audit
    rows = {
        r["signal_name"]: float(r["weight"])
        for r in await pool.fetch(
            "SELECT signal_name, weight FROM signal_weight_current WHERE status='effective'"
        )
    }
    assert rows["factor"] == pytest.approx(0.32)


# --- inversion guard (2026-07-05): persistently negative IC -> zeroed ---

from alpha_agent.fusion.guarded_weights import (  # noqa: E402
    inverted_signals,
    inverted_signals_from_series,
)


def test_inversion_rule_pure():
    series = {
        "options": [-0.04, -0.05, -0.02, -0.03, -0.06, -0.01, -0.04, -0.05],  # inverted
        "factor": [0.02, 0.01, 0.03, 0.02, 0.01, 0.02, 0.03, 0.01],           # healthy
        "mixed": [-0.04, 0.05, -0.02, 0.06, -0.01, 0.04, 0.03, 0.02],         # mean>-0.01
        "thin": [-0.5, -0.4],                                                  # too few points
    }
    inv = inverted_signals_from_series(series)
    assert inv == {"options"}


async def _seed_ic_recent(pool, sig, ics):
    """IC history INSIDE the guard's trailing 30d window (now()-based)."""
    from datetime import UTC, datetime, timedelta
    now = datetime.now(UTC)
    for i, ic in enumerate(ics):
        await pool.execute(
            "INSERT INTO signal_ic_history "
            "(signal_name, window_days, horizon_days, computed_at, ic, n_observations) "
            "VALUES ($1, 30, 5, $2, $3, 50)",
            sig, now - timedelta(days=len(ics) - i), float(ic),
        )


@pytest.mark.asyncio
async def test_inversion_guard_zeroes_and_logs_transitions(pool):
    static = {"factor": 0.30, "options": 0.10}
    await _seed_adaptive(pool, {"factor": 0.50, "options": 0.50})
    await _seed_ic_recent(pool, "factor", [0.02] * 12)          # healthy, eligible
    await _seed_ic_recent(pool, "options", [-0.04] * 12)        # persistently inverted

    eff = await get_effective_weights(pool, static=static, alpha=0.10, persist=True)
    assert eff["factor"] == pytest.approx(0.32)   # normal guarded blend
    assert eff["options"] == 0.0                   # zeroed by the guard

    # guard state row exists while zeroed; the flip was logged ONCE
    inv = await inverted_signals(pool)
    assert inv == {"options"}
    guard_rows = await pool.fetch(
        "SELECT signal_name FROM signal_weight_current WHERE status='inversion_guard'"
    )
    assert [r["signal_name"] for r in guard_rows] == ["options"]
    logs = await pool.fetch(
        "SELECT new_value FROM config_change_log WHERE source='inversion_guard'"
    )
    assert len(logs) == 1 and "zeroed" in logs[0]["new_value"]

    # second fusion: still zeroed, but NO duplicate log row (transition-only)
    await get_effective_weights(pool, static=static, alpha=0.10, persist=True)
    logs2 = await pool.fetch(
        "SELECT id FROM config_change_log WHERE source='inversion_guard'"
    )
    assert len(logs2) == 1


@pytest.mark.asyncio
async def test_inversion_guard_lifts_on_recovery(pool):
    static = {"options": 0.10}
    await _seed_adaptive(pool, {"options": 0.50})
    await _seed_ic_recent(pool, "options", [-0.04] * 12)
    eff = await get_effective_weights(pool, static=static, persist=True)
    assert eff["options"] == 0.0

    # IC recovers: wipe the negative history, seed positive
    await pool.execute("DELETE FROM signal_ic_history WHERE signal_name='options'")
    await _seed_ic_recent(pool, "options", [0.03] * 12)
    eff2 = await get_effective_weights(pool, static=static, persist=True)
    assert eff2["options"] > 0.0                   # guard lifted
    guard_rows = await pool.fetch(
        "SELECT 1 FROM signal_weight_current WHERE status='inversion_guard'"
    )
    assert guard_rows == []                        # state row removed
    logs = await pool.fetch(
        "SELECT new_value FROM config_change_log WHERE source='inversion_guard' "
        "ORDER BY id"
    )
    assert len(logs) == 2 and "active" in logs[1]["new_value"]  # zero then lift
