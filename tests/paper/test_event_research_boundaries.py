from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from alpha_agent.data.option_observatory import observation, sample_options, select_contracts
from alpha_agent.paper.decision_evidence import screen_actions
from alpha_agent.orchestrator.alert_detector import detect_alerts


def contract(exp="2026-11-25", side="call", strike=102, root="NVDA"):
    return {
        "symbol": f"{root}:{exp}:{side}:{strike}",
        "root_symbol": root,
        "underlying_symbol": "NVDA",
        "expiration_date": exp,
        "type": side,
        "strike_price": str(strike),
    }


def test_private_chain_scope_and_marks():
    day = date(2026, 11, 24)
    records = [
        contract(exp, side, strike)
        for exp in ("2026-11-24", "2026-11-25", "2026-11-27", "2026-11-30")
        for side in ("call", "put")
        for strike in (98, 99, 100, 101, 102)
    ] + [contract(root="NVDA1")]
    chosen = select_contracts(records, "NVDA", 100, day)
    assert len(chosen) == 12 and {c["expiration_date"] for c in chosen} == {
        "2026-11-25",
        "2026-11-27",
    }
    assert {c["strike_price"] for c in chosen} == {"99", "100", "101"}
    now = datetime(2026, 11, 24, 16, tzinfo=UTC)
    q = observation(chosen[0], {}, now)
    assert q["iv"] is q["oi"] is q["oi_as_of"] is q["quote_at"] is None
    for age, expected in [(0, "indicative"), (901, "stale"), (-1, "future")]:
        q = observation(
            chosen[0],
            {"latestQuote": {"bp": 1, "ap": 2, "t": (now - timedelta(seconds=age)).isoformat()}},
            now,
        )
        assert q["quality"] == expected


@pytest.mark.asyncio
async def test_opt_in_precedes_db_and_network(monkeypatch):
    monkeypatch.delenv("PRIVATE_OPTION_RESEARCH", raising=False)
    pool = AsyncMock()
    assert await sample_options(pool) == {"status": "disabled"}
    pool.fetch.assert_not_called()


def test_shadow_screen_does_not_censor_exits_or_accept_rank_chasing():
    context = {
        "instruments": [
            {"instrument_id": "1", "ticker": "X"},
            {"instrument_id": "2", "ticker": "Y"},
        ],
        "account": {"portfolio_value": 100, "positions": [{"qty": 2, "ticker": "X"}]},
        "recommendations": [
            {
                "ticker": "Y",
                "rank": 1,
                "tier": "OW",
                "previous_tier": "OW",
                "evidence_id": "rating:7",
            }
        ],
    }
    result = {
        "decision": {
            "actions": [
                {"type": "set_target_weight", "target_weight": 0, "instrument_id": "1"},
                {
                    "type": "set_target_weight",
                    "target_weight": 0.1,
                    "instrument_id": "2",
                    "evidence_ids": ["rating:7"],
                },
            ]
        }
    }
    assert [r["disposition"] for r in screen_actions(context, result)] == [
        "review_risk_reduction",
        "withhold_unproven_replacement",
    ]


def test_missing_iv_percentile_is_not_a_spike():
    card = {
        "ticker": "NVDA",
        "rating": "HOLD",
        "composite_score": 0,
        "breakdown": [{"signal": "options", "z": 0.5, "raw": {"iv_percentile": None}}],
    }
    assert "iv_spike" not in {a["type"] for a in detect_alerts(None, card)}


@pytest.mark.asyncio
async def test_shadow_review_samples_unsolved_positions_as_unknown(applied_db):
    import asyncpg
    from alpha_agent.paper.event_shadow_policy import POLICY
    from alpha_agent.paper.event_shadow_review import record_session_sample, review_gate

    conn = await asyncpg.connect(applied_db)
    try:
        now = datetime(2026, 11, 23, 20, 57, tzinfo=UTC)
        for sleeve in ("no_trade", "long_only", "long_short"):
            await conn.execute(
                "INSERT INTO event_shadow_book(sleeve,initial_cash,free_cash) VALUES($1,100000,100000)",
                sleeve,
            )
        await record_session_sample(conn, now)
        result = await review_gate(conn)
        assert result["observed_sessions"] == 1 and not result["review_eligible"]
        await conn.execute(
            """INSERT INTO event_shadow_trial(policy,event_id,event_key,sleeve,ticker,direction,rule,event_evidence,
                  decision_at,entry_after,entry_until,status,reason,updated_at,qty,entry_price,entry_at)
              VALUES($1,1,'test-release','long_only','NVDA','long','test','{}',$2,$2,$2::timestamptz+interval '1 hour',
                  'open','test',$2,1,100,$2)""",
            POLICY,
            now,
        )
        await record_session_sample(conn, now + timedelta(minutes=1))
        result = await review_gate(conn)
        assert result["observed_sessions"] == 0 and result["metrics"]["long_only"]["return"] is None
        assert not result["auto_promote"]
    finally:
        await conn.close()
