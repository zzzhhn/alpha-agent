"""Phase A: the factor_lessons memory layer — persistent experiment journal the
proposer reads (recent lessons + tried expressions) and writes (one distilled
lesson per candidate outcome). Pure helpers are unit-tested; CRUD runs against
the ephemeral migrated Postgres (applied_db)."""
import asyncpg
import pytest

from alpha_agent.storage import factor_lessons as fl


# ── pure helpers ────────────────────────────────────────────────────

def test_extract_operators_dedups_in_order():
    assert fl.extract_operators("rank(ts_mean(returns, 12))") == ["rank", "ts_mean"]
    assert fl.extract_operators("add(rank(x), rank(y))") == ["add", "rank"]
    assert fl.extract_operators("") == []


def test_distill_lesson_variants():
    keep = fl.distill_lesson(
        expression="rank(x)", outcome="accepted", test_sharpe=2.1, test_ic=0.03
    )
    assert keep.startswith("KEEP") and "2.1" in keep and "rank(x)" in keep

    avoid = fl.distill_lesson(
        expression="divide(x, x)", outcome="rejected", reject_reason="degenerate"
    )
    assert avoid.startswith("AVOID") and "degenerate" in avoid

    weak = fl.distill_lesson(expression="rank(y)", outcome="weak", test_sharpe=0.2)
    assert weak.startswith("WEAK") and "0.2" in weak


# ── CRUD against migrated Postgres ──────────────────────────────────

@pytest.mark.asyncio
async def test_record_and_load_roundtrip(applied_db):
    pool = await asyncpg.create_pool(applied_db, min_size=1, max_size=2)
    try:
        await fl.record_lesson(
            pool, expression="rank(ts_mean(returns, 8))", outcome="accepted",
            test_sharpe=2.0, test_ic=0.03, deflated_sharpe=1.1,
        )
        await fl.record_lesson(
            pool, expression="divide(x, x)", outcome="rejected",
            reject_reason="degenerate",
        )

        lessons = await fl.load_recent_lessons(pool, limit=10)
        assert len(lessons) == 2
        # most-recent-first ordering
        assert lessons[0].startswith("AVOID")

        tried = await fl.load_tried_expressions(pool, limit=10)
        assert "rank(ts_mean(returns, 8))" in tried
        assert "divide(x, x)" in tried
    finally:
        await pool.close()


@pytest.mark.asyncio
async def test_tried_expressions_are_deduped(applied_db):
    pool = await asyncpg.create_pool(applied_db, min_size=1, max_size=2)
    try:
        # same expression tried twice → appears once in the tried list
        for _ in range(2):
            await fl.record_lesson(
                pool, expression="rank(close)", outcome="weak", test_sharpe=0.4
            )
        tried = await fl.load_tried_expressions(pool, limit=10)
        assert tried.count("rank(close)") == 1
    finally:
        await pool.close()
