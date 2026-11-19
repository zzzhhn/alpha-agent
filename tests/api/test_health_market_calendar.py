"""Health windows must follow the scheduler without hiding missing work."""
from datetime import UTC, datetime, timedelta
import json

import asyncpg
import pytest

from alpha_agent.api.routes import health


async def seed_receipt(conn, name, instant, market_date, i, ok=True, expected=8):
    details = {}
    if name in ("fast_intraday", "daily_prices"):
        details = {"unit": name, "market_date": str(market_date),
                   "offset": i * (75 if name == "daily_prices" else 40)}
        if name == "daily_prices":
            details["expected_shards"] = expected
        name = "tick_daily_close"
    await conn.execute(
        "INSERT INTO cron_runs(cron_name,started_at,finished_at,ok,error_count,details) "
        "VALUES($1,$2,$2,$3,$4,$5::jsonb)", name, instant, ok, int(not ok), json.dumps(details))


@pytest.mark.parametrize(("instant", "session"), [
    ("2026-11-15T12:00:00+00:00", "2026-11-13"),  # Sunday
    ("2026-11-16T23:59:00+00:00", "2026-11-13"),  # Monday tick still has time
    ("2026-11-17T00:00:00+00:00", "2026-11-16"),  # next deadline
    ("2026-11-27T12:00:00+00:00", "2026-11-25"),  # Thanksgiving
    ("2026-11-28T12:00:00+00:00", "2026-11-27"),  # shortened Friday
    ("2026-03-09T12:00:00+00:00", "2026-03-06"),  # DST weekend
])
def test_session_window_and_wall_clock_jobs(instant, session):
    now = datetime.fromisoformat(instant)
    windows, required = health._dag_windows(now)
    assert required == session
    assert windows["daily_prices"] == datetime.fromisoformat(session).replace(tzinfo=UTC)
    assert windows["paper_fill"] == now - timedelta(hours=48)
    assert windows["ic_backtest_monthly"] == now - timedelta(days=35)


@pytest.mark.parametrize(("case", "expected"), [
    ("complete", "healthy"),
    ("missing_friday", "missing"),
    ("failed_shard", "failed"),
    ("missing_shard", "incomplete"),
    ("duplicate", "incomplete"),
    ("recovered", "healthy"),
    ("small_universe", "healthy"),
    ("late_old_publish", "stale"),
])
async def test_weekend_dag_uses_durable_session_evidence(
    client_with_db, applied_db, monkeypatch, case, expected,
):
    now = datetime(2026, 11, 15, 12, tzinfo=UTC)

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    monkeypatch.setattr(health, "datetime", FrozenDatetime)
    observed = datetime(2026, 11, 13, 22, 30, tzinfo=UTC)
    if case == "missing_friday":
        observed -= timedelta(days=1)
    conn = await asyncpg.connect(applied_db)
    try:
        for name, requirement in health._DAG_REQUIREMENTS.items():
            if name == "recommendation_publish":
                continue
            count = requirement["required_runs"]
            if name == "daily_prices" and case == "small_universe":
                count = 3
            if name == "daily_prices" and case == "missing_shard":
                count -= 1
            for i in range(count):
                ok = not (name == "daily_prices" and case == "failed_shard" and i == 0)
                if case == "recovered" and i == 0 and name == "daily_prices":
                    await seed_receipt(conn, name, observed, observed.date(), i, False)
                offset_idx = 0 if name == "daily_prices" and case == "duplicate" else i
                await seed_receipt(conn, name, observed, observed.date(), offset_idx, ok,
                                   3 if case == "small_universe" else 8)
        market_date = observed.date()
        if case == "late_old_publish":
            market_date -= timedelta(days=1)
        await conn.execute(
            "INSERT INTO research_run(scheduled_for_date,status,started_at,finished_at) "
            "VALUES($1,'complete',$2,$2)", market_date, observed,
        )
    finally:
        await conn.close()

    body = client_with_db.get("/api/_health/dag").json()
    nodes = {node["name"]: node for node in body["nodes"]}
    target = "recommendation_publish" if case == "late_old_publish" else "daily_prices"
    assert nodes[target]["status"] == expected
    assert nodes[target]["required_market_date"] == "2026-11-13"
    assert body["overall"] == ("healthy" if expected == "healthy" else "degraded")
