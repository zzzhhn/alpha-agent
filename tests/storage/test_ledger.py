# tests/storage/test_ledger.py
"""record_daily_close: snapshot the canonical picks view into the ledger.

Golden round-trip — the council's correctness bar: the recorded
user_visible_payload is byte-identical to what build_lean_view produces (which
the /api/picks/lean endpoint also serves, verified separately in
tests/api/test_picks.py), so the immutable record never drifts from what the
user saw. Plus the idempotent-skip: only the first complete run of a market
date is recorded; a re-fire is a no-op (append-only, never a silent overwrite).
"""
import json
from datetime import date

import pytest

from alpha_agent.api.routes.picks import build_lean_view
from alpha_agent.ledger import record_daily_close
from alpha_agent.storage.postgres import close_pool, get_pool
from alpha_agent.storage.product_ledger import get_canonical_run, get_run_snapshots


@pytest.fixture
async def pool(applied_db):
    p = await get_pool(applied_db)
    yield p
    await close_pool()


async def _seed(pool, rows):
    today = date.today()
    for tk, comp, rating in rows:
        await pool.execute(
            "INSERT INTO daily_signals_fast "
            "(ticker, date, composite, rating, confidence, breakdown, partial) "
            "VALUES ($1, $2, $3, $4, 0.8, '{\"breakdown\": []}'::jsonb, false)",
            tk, today, comp, rating,
        )


@pytest.mark.asyncio
async def test_record_daily_close_golden_roundtrip(pool):
    await _seed(pool, [("AAA", 2.0, "BUY"), ("BBB", 1.0, "HOLD"), ("CCC", 1.5, "OW")])
    # The exact view the user saw (endpoint + ledger share build_lean_view).
    cards, _as_of, _stale = await build_lean_view(
        pool, limit=600, search=None, mode="short", side="long"
    )
    assert [c.ticker for c in cards] == ["AAA", "CCC", "BBB"]

    run_id = await record_daily_close(pool, scheduled_for_date=date.today())
    assert run_id is not None

    snaps = await get_run_snapshots(pool, run_id)
    assert len(snaps) == len(cards)
    for i, (snap, card) in enumerate(zip(snaps, cards), start=1):
        assert snap["ticker"] == card.ticker
        assert snap["rank"] == i
        assert snap["tier"] == card.rating
        assert snap["composite_z"] == pytest.approx(card.composite_score)
        assert snap["eligible"] is True
        # The crux: the persisted payload IS the card the user saw.
        assert json.loads(snap["user_visible_payload_json"]) == card.model_dump()

    run = await get_canonical_run(pool, date.today())
    assert run["id"] == run_id
    assert run["weight_policy_id"]  # provenance stamped (deterministic)
    assert run["data_asof"] is not None  # carries the view's as_of


@pytest.mark.asyncio
async def test_record_daily_close_is_idempotent_per_day(pool):
    await _seed(pool, [("AAA", 2.0, "BUY")])
    first = await record_daily_close(pool, scheduled_for_date=date.today())
    second = await record_daily_close(pool, scheduled_for_date=date.today())
    assert first is not None
    assert second is None  # already recorded today -> skip, not overwrite

    n_runs = await pool.fetchval("SELECT count(*) FROM research_run")
    assert n_runs == 1


@pytest.mark.asyncio
async def test_record_daily_close_empty_view_still_records_provenance(pool):
    # No signals yet: the engine emitted nothing, but the run + its provenance
    # are still worth recording (gates in step 2 decide tradability).
    run_id = await record_daily_close(pool, scheduled_for_date=date.today())
    assert run_id is not None
    snaps = await get_run_snapshots(pool, run_id)
    assert snaps == []
