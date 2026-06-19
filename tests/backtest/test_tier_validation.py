# tests/backtest/test_tier_validation.py
"""Signal pruning by incremental contribution + tier monotonicity (step 7).

Two NON-destructive diagnostics (they flag/report; they never delete a signal):
  - prune_candidates: a signal is a prune candidate ONLY IF every weak-signal
    criterion holds at once (low IC AND redundant AND poor coverage AND high
    maintenance AND no forward/L2 contribution). NEVER on low IC alone — a
    decorrelated, cheap, low-turnover signal that still contributes stays
    (council split-5: do not hard-drop RSRS by IC).
  - tier_monotonicity: per-tier forward return / hit-rate / count from the
    ledger snapshots vs daily_prices; checks BUY >= OW >= HOLD >= UW >= SELL.
"""
from datetime import UTC, date, datetime

import pytest

from alpha_agent.backtest.tier_validation import prune_candidates, tier_monotonicity
from alpha_agent.storage.postgres import close_pool, get_pool
from alpha_agent.storage.product_ledger import RatingSnapshot, RunMeta, record_research_run


# --- prune_candidates (pure) ---

def _weak():
    return {"ic": 0.005, "max_corr": 0.9, "coverage": 0.2,
            "maintenance": 0.9, "forward_contribution": 0.0}


def test_low_ic_alone_is_not_pruned():
    # Low IC but decorrelated + good coverage + cheap + still contributes (RSRS-like).
    m = {"rsrs": {"ic": 0.005, "max_corr": 0.1, "coverage": 0.9,
                  "maintenance": 0.1, "forward_contribution": 0.03}}
    assert prune_candidates(m) == []


def test_all_criteria_met_is_flagged():
    out = prune_candidates({"dud": _weak()})
    assert [c["signal"] for c in out] == ["dud"]
    # every criterion is reported (transparency)
    assert set(out[0]["reasons"]) == {
        "low_ic", "redundant", "poor_coverage", "high_maintenance", "no_forward_contribution",
    }


def test_one_strong_dimension_spares_the_signal():
    m = _weak()
    m["forward_contribution"] = 0.05  # contributes despite everything else weak
    assert prune_candidates({"x": m}) == []


# --- tier_monotonicity (DB) ---

@pytest.fixture
async def pool(applied_db):
    p = await get_pool(applied_db)
    yield p
    await close_pool()


async def _seed(pool, d, picks, price_paths):
    """picks: [(ticker, tier)]; price_paths: {ticker: [closes over consecutive days from d]}."""
    snaps = [RatingSnapshot(ticker=t, tier=tier, rank=i + 1, eligible=True)
             for i, (t, tier) in enumerate(picks)]
    meta = RunMeta(scheduled_for_date=d, status="complete",
                   started_at=datetime(2026, 6, 15, tzinfo=UTC),
                   finished_at=datetime(2026, 6, 15, 1, tzinfo=UTC))
    await record_research_run(pool, meta, snaps)
    from datetime import timedelta
    for tk, closes in price_paths.items():
        for i, c in enumerate(closes):
            await pool.execute(
                "INSERT INTO daily_prices (ticker, date, close) VALUES ($1, $2, $3) "
                "ON CONFLICT (ticker, date) DO UPDATE SET close=EXCLUDED.close",
                tk, d + timedelta(days=i), c,
            )


@pytest.mark.asyncio
async def test_tier_monotonicity_detects_correct_ordering(pool):
    d = date(2026, 6, 15)
    await _seed(pool, d,
                [("BUP", "BUY"), ("SDN", "SELL")],
                {"BUP": [100.0, 105.0, 110.0],   # +10% over 2 days
                 "SDN": [100.0, 95.0, 90.0]})    # -10%
    rep = await tier_monotonicity(pool, horizon_days=2)
    assert rep["tiers"]["BUY"]["mean_ret"] == pytest.approx(0.10)
    assert rep["tiers"]["SELL"]["mean_ret"] == pytest.approx(-0.10)
    assert rep["tiers"]["BUY"]["hit_rate"] == pytest.approx(1.0)
    assert rep["monotonic"] is True
    assert rep["violations"] == []


@pytest.mark.asyncio
async def test_tier_monotonicity_flags_inversion(pool):
    d = date(2026, 6, 15)
    await _seed(pool, d,
                [("BUP", "BUY"), ("SUP", "SELL")],
                {"BUP": [100.0, 100.0, 100.0],   # flat
                 "SUP": [100.0, 105.0, 110.0]})  # SELL rallied -> inversion
    rep = await tier_monotonicity(pool, horizon_days=2)
    assert rep["monotonic"] is False
    assert rep["violations"]  # BUY < SELL recorded
