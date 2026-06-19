# tests/storage/test_product_ledger.py
"""Behavior tests for the append-only product-ledger writer/reader.

These pin the contract the council called the engine's #1 prerequisite:
  - a run + its snapshots persist and round-trip exactly (provenance + the
    user-visible payload come back byte-identical);
  - the ledger is append-only: re-recording a complete run for the same date
    is refused by default, and an explicit correction adds a NEW run without
    ever mutating the earlier one;
  - the canonical run for a date is the latest COMPLETE run by finished_at;
    partial / failed runs are never canonical.
"""
from datetime import UTC, date, datetime

import pytest

from alpha_agent.storage.postgres import close_pool, get_pool
from alpha_agent.storage.product_ledger import (
    LedgerConflict,
    RatingSnapshot,
    RunMeta,
    get_canonical_run,
    get_run_snapshots,
    record_research_run,
)


@pytest.fixture
async def pool(applied_db):
    p = await get_pool(applied_db)
    yield p
    await close_pool()


def _meta(*, status="complete", finished_at=None, for_date=date(2026, 6, 18)):
    started = datetime(2026, 6, 18, 21, 0, tzinfo=UTC)
    return RunMeta(
        scheduled_for_date=for_date,
        status=status,
        started_at=started,
        finished_at=finished_at or datetime(2026, 6, 18, 21, 5, tzinfo=UTC),
        data_asof=datetime(2026, 6, 18, 20, 0, tzinfo=UTC),
        input_data_cutoff=datetime(2026, 6, 18, 20, 0, tzinfo=UTC),
        code_version="abc1234",
        registry_hash="reg-hash-1",
        weight_policy_id="STATIC_V2",
        tier_threshold_version="tiers-v1",
    )


def _snap(ticker, rank, tier="BUY"):
    return RatingSnapshot(
        ticker=ticker,
        composite_z=1.5 - rank * 0.1,
        rank=rank,
        tier=tier,
        coverage=0.8,
        eligible=True,
        effective_weight={"technicals": 0.15, "rsrs": 0.05},
        user_visible_payload={"ticker": ticker, "rating": tier, "rank": rank},
        price_source="yfinance",
        adjustment_mode="adjusted",
        feed_status="fresh",
    )


@pytest.mark.asyncio
async def test_record_and_roundtrip(pool):
    run_id = await record_research_run(
        pool, _meta(), [_snap("AAPL", 1), _snap("MSFT", 2, "OW")]
    )
    assert isinstance(run_id, int)

    snaps = await get_run_snapshots(pool, run_id)
    by_ticker = {s["ticker"]: s for s in snaps}
    assert set(by_ticker) == {"AAPL", "MSFT"}

    import json

    aapl = by_ticker["AAPL"]
    assert aapl["rank"] == 1
    assert aapl["tier"] == "BUY"
    assert aapl["feed_status"] == "fresh"
    assert json.loads(aapl["user_visible_payload_json"]) == {
        "ticker": "AAPL", "rating": "BUY", "rank": 1,
    }
    assert json.loads(aapl["effective_weight_json"]) == {
        "technicals": 0.15, "rsrs": 0.05,
    }

    run = await get_canonical_run(pool, date(2026, 6, 18))
    assert run is not None
    assert run["id"] == run_id
    assert run["weight_policy_id"] == "STATIC_V2"


@pytest.mark.asyncio
async def test_duplicate_complete_refused_by_default(pool):
    await record_research_run(pool, _meta(), [_snap("AAPL", 1)])
    with pytest.raises(LedgerConflict):
        await record_research_run(pool, _meta(), [_snap("AAPL", 1)])


@pytest.mark.asyncio
async def test_correction_appends_without_mutating_original(pool):
    run1 = await record_research_run(
        pool,
        _meta(finished_at=datetime(2026, 6, 18, 21, 5, tzinfo=UTC)),
        [_snap("AAPL", 1)],
    )
    # A correction: new finished_at, different ranking, opted in.
    run2 = await record_research_run(
        pool,
        _meta(finished_at=datetime(2026, 6, 18, 23, 0, tzinfo=UTC)),
        [_snap("AAPL", 5, "HOLD")],
        allow_correction=True,
    )
    assert run2 != run1

    # The original run is untouched (append-only).
    orig = await get_run_snapshots(pool, run1)
    assert orig[0]["rank"] == 1
    assert orig[0]["tier"] == "BUY"

    # The canonical run is the later correction.
    canon = await get_canonical_run(pool, date(2026, 6, 18))
    assert canon["id"] == run2
    canon_snaps = await get_run_snapshots(pool, run2)
    assert canon_snaps[0]["rank"] == 5
    assert canon_snaps[0]["tier"] == "HOLD"


@pytest.mark.asyncio
async def test_partial_and_failed_runs_are_never_canonical(pool):
    await record_research_run(pool, _meta(status="partial"), [_snap("AAPL", 1)])
    await record_research_run(pool, _meta(status="failed"), [])
    assert await get_canonical_run(pool, date(2026, 6, 18)) is None


@pytest.mark.asyncio
async def test_health_json_roundtrips(pool):
    import json
    health = {"passed": True, "reasons": [], "metrics": {"eligible_count": 42}}
    meta = RunMeta(
        scheduled_for_date=date(2026, 6, 18),
        status="complete",
        started_at=datetime(2026, 6, 18, 21, 0, tzinfo=UTC),
        finished_at=datetime(2026, 6, 18, 21, 5, tzinfo=UTC),
        health=health,
    )
    run_id = await record_research_run(pool, meta, [_snap("AAPL", 1)])
    row = await pool.fetchrow("SELECT health_json FROM research_run WHERE id=$1", run_id)
    assert json.loads(row["health_json"]) == health


@pytest.mark.asyncio
async def test_partial_does_not_block_a_later_complete(pool):
    # A partial run earlier in the day must not trip the duplicate guard.
    await record_research_run(pool, _meta(status="partial"), [_snap("AAPL", 1)])
    run_complete = await record_research_run(
        pool,
        _meta(status="complete", finished_at=datetime(2026, 6, 18, 23, 0, tzinfo=UTC)),
        [_snap("AAPL", 1)],
    )
    canon = await get_canonical_run(pool, date(2026, 6, 18))
    assert canon["id"] == run_complete
