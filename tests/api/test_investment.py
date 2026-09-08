import asyncpg
import httpx
import pytest
from pydantic import ValidationError

from alpha_agent.api.routes.investment import InvestmentProfile, review_holdings
from alpha_agent.auth.dependencies import require_user


def profile(**overrides):
    return {"horizon_months": 12, "drawdown_review_pct": 15,
            "review_frequency": "monthly", "max_position_pct": 10,
            "max_sector_pct": 20, "holdings_as_of": "2026-08-31",
            "holdings": [{"ticker": "AAPL", "weight_pct": 15}], **overrides}


def test_profile_caps_missing_sector_and_invalid_allocations():
    p = InvestmentProfile.model_validate(profile())
    r = review_holdings(p, {})
    assert r["warnings"][0]["code"] == "position_limit"
    assert r["unknown_sector_tickers"] == ["AAPL"]
    assert r["unallocated_pct"] == 85
    assert r["orders_created"] == 0
    with pytest.raises(ValidationError):
        InvestmentProfile.model_validate(profile(holdings=[{"ticker": "AAA", "weight_pct": 60}, {"ticker": "BBB", "weight_pct": 60}]))
    with pytest.raises(ValidationError):
        InvestmentProfile.model_validate(profile(holdings=[{"ticker": "aapl", "weight_pct": 10}, {"ticker": "AAPL", "weight_pct": 5}]))


async def test_profile_private_persistence_and_isolation(client_with_db, applied_db):
    app = client_with_db.app
    c = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    assert (await c.get("/api/user/investment/profile")).status_code == 401
    conn = await asyncpg.connect(applied_db)
    try:
        await conn.execute("INSERT INTO users(id,email) VALUES(1,'one@example.test'),(2,'two@example.test')")
        await conn.execute("INSERT INTO user_preferences(user_id,extras) VALUES(1,'{\"unrelated\":true}')")
        app.dependency_overrides[require_user] = lambda: 1
        assert (await c.post("/api/user/investment/profile", json=profile())).status_code == 200
        result = await c.get("/api/user/investment/profile")
        assert result.json()["profile"]["horizon_months"] == 12
        assert "no-store" in result.headers["cache-control"]
        assert await conn.fetchval("SELECT (extras->>'unrelated')::boolean FROM user_preferences WHERE user_id=1")
        assert (await c.get("/api/user/investment/review")).json()["orders_created"] == 0
        thesis = {"ticker": "aapl", "rationale": "earnings", "counterevidence": "valuation",
                  "invalidation": "earnings miss", "source_notes": "filing, verify", "next_review": "2026-09-30"}
        saved = await c.post("/api/user/investment/theses", json=thesis)
        assert saved.status_code == 200
        assert saved.json()["entry"]["revision"] == 1
        assert (await c.post("/api/user/investment/theses", json=thesis)).status_code == 409
        assert len((await c.get("/api/user/investment/theses")).json()["entries"]) == 1
        assert (await c.get("/api/user/investment/profile")).json()["profile"]["horizon_months"] == 12
        app.dependency_overrides[require_user] = lambda: 2
        assert (await c.get("/api/user/investment/profile")).json()["profile"] is None
        assert (await c.get("/api/user/investment/theses")).json()["entries"] == []
        assert (await c.post("/api/user/investment/profile", json=profile(user_id=1))).status_code == 422
    finally:
        app.dependency_overrides.clear()
        await c.aclose()
        await conn.close()


async def test_evidence_uses_only_requested_continuous_book(client_with_db, applied_db):
    from alpha_agent.backtest.l2_continuous import ensure_book
    from datetime import date
    conn = await asyncpg.connect(applied_db)
    try:
        tactical = await ensure_book(conn, sleeve="tactical", start_after_run_id=0)
        strategic = await ensure_book(conn, sleeve="strategic", start_after_run_id=0)
        for sid, nav in [(tactical, 1100000), (strategic, 900000)]:
            await conn.execute("UPDATE l2_account SET nav=$1,last_fill_date=$2 WHERE strategy_id=$3", nav, date(2026, 9, 4), sid)
            await conn.execute("INSERT INTO l2_equity_daily(strategy_id,as_of_date,nav,net_return) VALUES($1,$2,1000000,0),($1,$3,$4,$5)", sid, date(2026, 8, 28), date(2026, 9, 4), nav, nav / 1000000 - 1)
        body = client_with_db.get("/api/l2/evidence?sleeve=strategic").json()
        assert body["account"]["strategy_id"] == strategic
        assert body["comparison"]["strategy"] == pytest.approx(-0.1)
        assert body["comparison"]["spy"] is None
        assert body["evidence_status"] == "unproven"
        assert client_with_db.get("/api/l2/evidence?sleeve=invalid").status_code == 422
    finally:
        await conn.close()
