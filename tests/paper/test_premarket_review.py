from datetime import timedelta

import asyncpg
import pytest

from alpha_agent.paper import premarket_review as p
from alpha_agent.paper.market_clock import as_utc


def test_exchange_windows_including_holiday_dst_and_early_close():
    for ts, stage in [
        ("2026-11-25T14:20Z", "premarket"),
        ("2026-07-01T13:20Z", "premarket"),
        ("2026-11-25T15:00Z", "open_review"),
        ("2026-11-27T18:05Z", "evaluation"),
    ]:
        assert p.slot(as_utc(ts))[1] == stage
    for ts in ("2026-11-26T14:20Z", "2026-11-25T14:25Z", "2026-11-27T21:05Z"):
        assert p.slot(as_utc(ts)) is None


def test_eligible_swaps_only_with_review_for_conflicts():
    names = [f"S{i}" for i in range(52)]

    def event(i, title):
        return dict(ticker=i, title=title, source="investor_relations", status="observed")

    events = [
        event("S0", "Cuts revenue guidance"),
        event("S50", "Raises revenue guidance"),
        event("XYZ", "CEO returns"),
        event("S51", "Raises revenue guidance"),
        event("S51", "Cuts revenue guidance"),
    ]
    notes, changes = p.classify(names, {"XYZ"}, events, True)
    assert changes == [dict(out="S0", into="S50")]
    assert next(n for n in notes if n["ticker"] == "XYZ")["held"]
    assert next(n for n in notes if n["ticker"] == "S51")["tag"] == "review"
    assert p.classify(names, set(), events, False)[1] == []


def test_exact_minute_returns_not_overnight_gap():
    start, end = as_utc("2026-11-25T15:03Z"), as_utc("2026-11-25T21:00Z")

    def bar(t):
        return dict(
            start=t,
            open=110.0,
            close=110.0,
            volume=25,
            price_basis="raw_unadjusted",
            corporate_actions_known=True,
            corporate_actions=[],
        )

    samples = [bar(start), bar(end - p.MIN)]
    assert -0.0041 < p.paired_return(samples, start, end) < -0.0039
    assert p.paired_return(samples, start + p.MIN, end) is None
    assert (
        p.paired_return([bar(start), dict(bar(end - p.MIN), corporate_actions=[{}])], start, end)
        is None
    )


@pytest.mark.asyncio
async def test_forward_receipts_and_late_event(applied_db, monkeypatch):
    pool = await asyncpg.create_pool(applied_db, min_size=1, max_size=2)
    now = as_utc("2026-11-25T14:20:01Z")
    try:
        owner = await pool.fetchval(
            "INSERT INTO users(email) VALUES ('premarket@test.invalid') RETURNING id"
        )
        run = await pool.fetchval(
            """INSERT INTO research_run(scheduled_for_date,status,started_at,finished_at)
            VALUES ('2026-11-24','complete',$1,$1) RETURNING id""",
            now - timedelta(hours=12),
        )
        await pool.execute(
            """INSERT INTO rating_snapshot(run_id,ticker,rank,composite_z)
            SELECT $1,'S'||x,x,100-x FROM generate_series(1,51) x""",
            run,
        )
        await pool.execute(
            """INSERT INTO official_event_source(ticker,source,last_success_at)
            VALUES ('S1','investor_relations',$1)""",
            now - p.MIN,
        )
        for t, offset in [("S1", -1), ("S51", 1)]:
            await pool.execute(
                """INSERT INTO official_event_watch(ticker,source,source_key,content_hash,title,url,
                published_at,published_at_quality,first_seen_at,kind,status) VALUES
                ($1,'investor_relations','release','hash',$2,'https://example.org',
                 $3,'source_timestamp',$4,'release','observed')""",
                t,
                "Cuts revenue guidance" if offset < 0 else "Raises revenue guidance",
                now - 2 * p.MIN,
                now + offset * p.MIN,
            )

        async def no_bars(*args):
            return []

        monkeypatch.setattr(p, "fetch_bars", no_bars)
        assert (await p.tick(pool, owner, lambda: now))["status"] == "recorded"
        assert (await p.tick(pool, owner, lambda: now))["status"] == "already_recorded"
        await pool.execute("UPDATE official_event_source SET last_success_at=$1", now + 39 * p.MIN)
        assert (await p.tick(pool, owner, lambda: now + 40 * p.MIN))["status"] == "recorded"
        assert (await p.tick(pool, owner, lambda: as_utc("2026-11-25T21:05Z")))[
            "status"
        ] == "recorded"
        rows = await pool.fetch("SELECT stage,payload FROM premarket_review ORDER BY captured_at")
        a, b, c = [p.unpack(row["payload"]) for row in rows]
        assert a["changes"] == [dict(out="S1", into=None)]
        assert b["changes"] == [dict(out="S1", into="S51")] and len(b["new_event_ids"]) == 1
        assert b["quotes"] == {"S1": None, "S51": None}
        assert c["results"]["premarket"]["status"] == "no_decision"
        # Separate appraisal, not a rewrite of the captured close or a bot wake.
        account = await pool.fetchval(
            """INSERT INTO sim_account(user_id,kind) VALUES ($1,'bot')
                                    RETURNING id""",
            owner,
        )
        action = as_utc("2026-11-25T15:02:04Z")
        await pool.execute(
            """INSERT INTO sim_bot_run(id,account_id,trigger,trading_session,status,
            finished_at,expires_at,config_version,config_snapshot,llm_calls,result)
            VALUES (gen_random_uuid(),$1,'open_after','2026-11-25','no_trade',$2,$2,1,'{}',1,
            '{"decision":{"decision":"no_trade"}}')""",
            account,
            action,
        )
        close = as_utc("2026-11-25T21:00Z")

        async def flat(ticker, _):
            return [
                dict(
                    start=t,
                    open=100,
                    close=100,
                    volume=100,
                    corporate_actions=[],
                    corporate_actions_known=True,
                    price_basis="raw_unadjusted",
                )
                for t in (as_utc("2026-11-25T15:03Z"), close - p.MIN)
            ]

        monkeypatch.setattr(p, "fetch_bars", flat)
        measured = await p.evaluate(pool, owner, action.date(), close, close + 5 * p.MIN)
        assert measured["results"]["premarket"]["delta_bps"] == pytest.approx(0.798, abs=0.002)
        assert measured["results"]["open_review"]["delta_bps"] == 0
        monkeypatch.setattr(p, "fetch_bars", no_bars)
        missing = await p.evaluate(pool, owner, action.date(), close, close + 5 * p.MIN)
        assert missing["results"]["premarket"]["delta_bps"] is None
        assert await pool.fetchval("SELECT count(*) FROM sim_order") == 0
    finally:
        await pool.close()
