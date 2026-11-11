"""Real-DB export coverage: ownership, allowlists, redaction, and row bounds."""
import json
from uuid import uuid4

import asyncpg
import httpx
import pytest

from alpha_agent.api.routes import user
from alpha_agent.auth.dependencies import require_user


@pytest.fixture
async def export_data(client_with_db, applied_db):
    conn = await asyncpg.connect(applied_db)
    app = client_with_db.app
    app.dependency_overrides[require_user] = lambda: 1
    try:
        await conn.execute("""
            INSERT INTO users(id,email,password_hash) VALUES
                (1,'one@example.test','SENSITIVE_HASH'),(2,'two@example.test','OTHER_HASH');
            INSERT INTO accounts("userId",type,provider,"providerAccountId",access_token,refresh_token)
                VALUES(1,'oauth','google','one','SENSITIVE_ACCESS','SENSITIVE_REFRESH');
            INSERT INTO password_reset_codes(email,code_hash,expires_at)
                VALUES('one@example.test','SENSITIVE_RESET',now()+interval '1 hour');
        """)
        ids = {1: {}, 2: {}}
        for uid in (1, 2):
            marker = f"owner-{uid}"
            extras = {
                "investment_profile": {"horizon_months": uid * 12, "holdings": [{"ticker": "AAA", "weight_pct": 10}]},
                "investment_theses": {ticker: {
                    "ticker": ticker, "rationale": marker, "counterevidence": "valuation",
                    "invalidation": "earnings", "source_notes": "filing",
                    "next_review": "2026-12-01", "status": "watch", "revision": 1,
                } for ticker in ("AAA", "BBB")},
                "unrelated_secret": "SENSITIVE_EXTRAS",
            }
            await conn.execute(
                "INSERT INTO user_preferences(user_id,extras) VALUES($1,$2::jsonb)",
                uid, json.dumps(extras),
            )
            await conn.execute(
                "INSERT INTO user_watchlist(user_id,ticker) VALUES($1,$2),($1,$3)",
                uid, marker + "-A", marker + "-B",
            )
            for provider in ("openai", "anthropic", "worldquant_brain"):
                await conn.execute(
                    "INSERT INTO user_byok(user_id,provider,ciphertext,nonce,last4,model) "
                    "VALUES($1,$2,$3,$4,'1234',$5)",
                    uid, provider, b"SENSITIVE_ENCRYPTED", b"SENSITIVE_NONCE",
                    "SENSITIVE_BRAIN" if provider == "worldquant_brain" else marker,
                )
            ids[uid]["accounts"] = []
            ids[uid]["brain"] = []
            for n, kind in enumerate(("human", "bot")):
                account_id = await conn.fetchval(
                    "INSERT INTO sim_account(user_id,kind,name) VALUES($1,$2,$3) RETURNING id",
                    uid, kind, marker,
                )
                ids[uid]["accounts"].append(account_id)
                await conn.execute(
                    "INSERT INTO sim_order(account_id,ticker,side,order_type,qty,signal_date,execution_evidence) "
                    "VALUES($1,$2,'buy','market',3,current_date,$3::jsonb)",
                    account_id, marker, json.dumps({"source": "close", "nested": {"access_token": "SENSITIVE_EVIDENCE"}}),
                )
                await conn.execute(
                    "INSERT INTO sim_position(account_id,ticker,qty,avg_cost) VALUES($1,$2,3,100)",
                    account_id, marker,
                )
                await conn.execute(
                    "INSERT INTO sim_equity_daily(account_id,as_of_date,portfolio_value,cash,unrealized_pnl,realized_pnl) "
                    "VALUES($1,current_date,1000000,999700,0,0)", account_id,
                )
                config = {"mode": marker, "ApiKey": "SENSITIVE_CONFIG", "nested": [
                    {"secret": "SENSITIVE_CONFIG", "PASSWORD": "SENSITIVE_CONFIG", "access_token": "SENSITIVE_CONFIG",
                     "refresh_token": "SENSITIVE_CONFIG", "ciphertext": "SENSITIVE_CONFIG", "nonce": "SENSITIVE_CONFIG",
                     "safe": {"threshold": 0.2}},
                ]}
                await conn.execute(
                    "INSERT INTO sim_bot_config(account_id,config) VALUES($1,$2::jsonb)",
                    account_id, json.dumps(config),
                )
                await conn.execute(
                    "INSERT INTO sim_bot_run(id,account_id,trigger,trading_session,expires_at,config_version,"
                    "config_snapshot,context,result,summary,provider,model,prompt_tokens,completion_tokens,llm_calls) "
                    "VALUES($1,$2,'manual',current_date,now()+interval '1 hour',1,"
                    "'{\"hidden\":\"SENSITIVE_SNAPSHOT\"}','{\"hidden\":\"SENSITIVE_CONTEXT\"}',"
                    "'{\"outcome_reason\":\"hold\",\"hidden\":\"SENSITIVE_RESULT\"}',$3,'openai','test',12,4,1)",
                    uuid4(), account_id, marker,
                )
                alert_id = await conn.fetchval(
                    "INSERT INTO alert_queue(ticker,type,dedup_bucket) VALUES($1,'test',$2) RETURNING id",
                    marker, n,
                )
                await conn.execute(
                    "INSERT INTO alert_triage_state(user_id,alert_id,note) VALUES($1,$2,$3)", uid, alert_id, marker,
                )
                ids[uid]["brain"].append(await conn.fetchval(
                    "INSERT INTO brain_runs(user_id,source,requested_n,error_detail) "
                    "VALUES($1,'manual',$2,'SENSITIVE_BRAIN_ERROR') RETURNING id", uid, uid,
                ))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test",
        ) as client:
            yield client, conn, ids
    finally:
        app.dependency_overrides.clear()
        await conn.close()


async def test_export_current_user_complete_without_secrets(export_data):
    client, conn, ids = export_data
    response = await client.get("/api/user/account/export")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    body = response.json()
    assert body["schema_version"] == 2
    assert body["user"]["email"] == "one@example.test"
    assert body["preferences"] == {"locale": "zh", "theme": "dark"}
    assert body["watchlist"] == ["owner-1-A", "owner-1-B"]
    assert {row["provider"] for row in body["byok_metadata"]} == {"openai", "anthropic"}
    assert {row["id"] for row in body["paper_accounts"]} == set(ids[1]["accounts"])
    assert {row["kind"] for row in body["paper_accounts"]} == {"human", "bot"}
    for section in ("orders", "positions", "daily_equity", "bot_config", "bot_runs"):
        assert {row["account_id"] for row in body[section]} == set(ids[1]["accounts"])
    # Migration-backed completeness check: every order column is explicitly exported.
    columns = await conn.fetch(
        "SELECT column_name FROM information_schema.columns WHERE table_name='sim_order' AND table_schema='public'",
    )
    assert set(body["orders"][0]) == {row["column_name"] for row in columns}
    assert body["orders"][0]["execution_evidence"] == {"source": "close", "nested": {}}
    assert body["bot_config"][0]["config"] == {
        "mode": "owner-1", "nested": [{"safe": {"threshold": 0.2}}],
    }
    assert body["bot_runs"][0]["result"] == {"outcome_reason": "hold"}
    assert body["bot_runs"][0]["prompt_tokens"] == 12
    assert body["bot_runs"][0]["completion_tokens"] == 4
    assert body["bot_runs"][0]["llm_calls"] == 1
    assert body["investment_profile"]["horizon_months"] == 12
    assert len(body["investment_notebook"]) == len(body["alert_triage_state"]) == 2
    assert {row["id"] for row in body["brain_runs"]} == set(ids[1]["brain"])
    assert body["brain_runs_available"] is True
    assert not any(body["truncated"].values())
    serialized = json.dumps(body).lower()
    for forbidden in ("ciphertext", "nonce", "password", "access_token", "refresh_token",
                      "sensitive_", "other_hash", "worldquant_brain", "owner-2", "two@example.test"):
        assert forbidden not in serialized


async def test_export_bounds_every_collection_and_flags_only_overflow(export_data, monkeypatch):
    client, _, _ = export_data
    monkeypatch.setattr(user, "_EXPORT_LIMIT", 1)
    body = (await client.get("/api/user/account/export")).json()
    for section, truncated in body["truncated"].items():
        if section == "investment_profile":
            assert truncated is False
        else:
            assert len(body[section]) == 1
            assert truncated is True, section
    monkeypatch.setattr(user, "_EXPORT_LIMIT", 2)
    body = (await client.get("/api/user/account/export")).json()
    assert not any(body["truncated"].values())


async def test_export_optional_brain_table_and_missing_user(client_with_db, applied_db):
    conn = await asyncpg.connect(applied_db)
    app = client_with_db.app
    try:
        await conn.execute("INSERT INTO users(id,email) VALUES(1,'one@example.test')")
        await conn.execute("DROP TABLE brain_runs CASCADE")
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.get("/api/user/account/export")).status_code == 401
            app.dependency_overrides[require_user] = lambda: 1
            body = (await client.get("/api/user/account/export")).json()
            assert body["brain_runs"] == []
            assert body["brain_runs_available"] is False
            assert body["truncated"]["brain_runs"] is False
            assert body["investment_profile"] is None
            assert body["investment_notebook"] == []
            app.dependency_overrides[require_user] = lambda: 999
            assert (await client.get("/api/user/account/export")).status_code == 404
    finally:
        app.dependency_overrides.clear()
        await conn.close()
