# tests/storage/test_ledger.py
"""record_daily_close: snapshot the canonical picks view into the ledger, gated.

Two contracts:
  - Golden round-trip (step 1 correctness bar): the recorded user_visible_payload
    is byte-identical to what build_lean_view produces (which /api/picks/lean
    also serves), so the immutable record never drifts from what the user saw.
  - Run-health gating (step 2): a healthy run is recorded 'complete' (canonical,
    tradable); a run that fails a hard gate (too few eligible / no benchmark) is
    recorded 'partial' with machine-readable reasons and is EXCLUDED from the
    canonical lookup, so L2 / forward-IC never consume it. Append-only either way.
"""
import json
from datetime import date

import pytest

from alpha_agent.api.routes.picks import build_lean_view
from alpha_agent.ledger import record_daily_close
from alpha_agent.run_health import MIN_ELIGIBLE
from alpha_agent.storage.postgres import close_pool, get_pool
from alpha_agent.storage.product_ledger import get_canonical_run, get_run_snapshots


@pytest.fixture
async def pool(applied_db):
    p = await get_pool(applied_db)
    yield p
    await close_pool()


async def _seed(pool, rows, *, benchmark=True):
    """Seed fast signal rows + a fresh close per ticker (so each passes the
    dead-feed guard and appears in the view) + optionally a fresh SPY close."""
    today = date.today()
    for tk, comp, rating in rows:
        await pool.execute(
            "INSERT INTO daily_signals_fast "
            "(ticker, date, composite, rating, confidence, breakdown, partial) "
            "VALUES ($1, $2, $3, $4, 0.8, '{\"breakdown\": []}'::jsonb, false)",
            tk, today, comp, rating,
        )
        await pool.execute(
            "INSERT INTO daily_prices (ticker, date, close) VALUES ($1, $2, 100.0)",
            tk, today,
        )
    if benchmark:
        await pool.execute(
            "INSERT INTO daily_prices (ticker, date, close) VALUES ('SPY', $1, 500.0)",
            today,
        )


def _many(n, start_comp=3.0):
    return [(f"T{i:03d}", start_comp - i * 0.01, "BUY") for i in range(n)]


@pytest.mark.asyncio
async def test_record_daily_close_golden_roundtrip(pool):
    await _seed(pool, [("AAA", 2.0, "BUY"), ("BBB", 1.0, "HOLD"), ("CCC", 1.5, "OW")])
    # The exact view the user saw (endpoint + ledger share build_lean_view).
    cards, _as_of, _stale = await build_lean_view(
        pool, limit=600, search=None, mode="short", side="long"
    )
    assert [c.ticker for c in cards] == ["AAA", "CCC", "BBB"]

    run_id = await record_daily_close(pool, scheduled_for_date=date.today(), min_eligible=2)
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
    assert run["id"] == run_id  # healthy -> complete -> canonical
    assert run["weight_policy_id"]
    assert run["data_asof"] is not None


@pytest.mark.asyncio
async def test_record_daily_close_is_idempotent_per_day(pool):
    await _seed(pool, [("AAA", 2.0, "BUY")])
    first = await record_daily_close(pool, scheduled_for_date=date.today(), min_eligible=1)
    second = await record_daily_close(pool, scheduled_for_date=date.today(), min_eligible=1)
    assert first is not None
    assert second is None  # already a complete run today -> skip, not overwrite
    assert await pool.fetchval("SELECT count(*) FROM research_run") == 1


@pytest.mark.asyncio
async def test_healthy_run_is_complete_with_metrics(pool):
    await _seed(pool, _many(MIN_ELIGIBLE + 1))  # over the default eligible gate
    run_id = await record_daily_close(pool, scheduled_for_date=date.today())  # default gate
    assert run_id is not None
    run = await get_canonical_run(pool, date.today())
    assert run["id"] == run_id
    health = json.loads(run["health_json"])
    assert health["passed"] is True
    assert health["metrics"]["eligible_count"] >= MIN_ELIGIBLE
    assert health["metrics"]["benchmark_fresh"] is True


@pytest.mark.asyncio
async def test_unhealthy_run_is_partial_and_excluded(pool):
    # 3 names (< MIN_ELIGIBLE) and no benchmark -> fails both hard gates.
    await _seed(pool, [("AAA", 2.0, "BUY"), ("BBB", 1.0, "HOLD"), ("CCC", 1.5, "OW")],
                benchmark=False)
    run_id = await record_daily_close(pool, scheduled_for_date=date.today())  # default gate
    assert run_id is not None  # the run IS recorded (forensics) ...
    assert await get_canonical_run(pool, date.today()) is None  # ... but not tradable

    row = await pool.fetchrow("SELECT status, health_json FROM research_run WHERE id=$1", run_id)
    assert row["status"] == "partial"
    health = json.loads(row["health_json"])
    assert health["passed"] is False
    assert any(r.startswith("insufficient_eligible") for r in health["reasons"])
    assert "no_benchmark" in health["reasons"]


@pytest.mark.asyncio
async def test_empty_view_is_partial_non_tradable(pool):
    # No signals at all: the engine emitted nothing -> non-tradable, but the run
    # + its provenance are still recorded (gates decide tradability, not silence).
    run_id = await record_daily_close(pool, scheduled_for_date=date.today())
    assert run_id is not None
    assert await get_run_snapshots(pool, run_id) == []
    assert await get_canonical_run(pool, date.today()) is None
