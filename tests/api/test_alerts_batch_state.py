from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import asyncpg
import httpx
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from alpha_agent.api.routes import alerts
from alpha_agent.auth.dependencies import require_user


@pytest_asyncio.fixture
async def alert_db_client(applied_db, monkeypatch):
    from api.index import app

    pool = await asyncpg.create_pool(applied_db, min_size=1, max_size=2)
    await pool.execute("INSERT INTO users(id,email) VALUES(7,'a@example.test'),(8,'b@example.test')")
    ids = []
    for bucket in (1, 2):
        ids.append(await pool.fetchval(
            "INSERT INTO alert_queue(ticker,type,payload,dedup_bucket,created_at) "
            "VALUES('AAPL','rating_change','{\"to\":\"UW\"}', $1, $2) RETURNING id",
            bucket, datetime.now(UTC).replace(hour=18, minute=bucket),
        ))
    monkeypatch.setattr(alerts, "get_db_pool", AsyncMock(return_value=pool))
    app.dependency_overrides[require_user] = lambda: 7
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test",
        ) as client:
            yield client, pool, ids, app
    finally:
        app.dependency_overrides.pop(require_user, None)
        await pool.close()


async def test_alert_batch_updates_only_current_user_and_reverts(alert_db_client):
    client, pool, ids, app = alert_db_client
    # Use the existing single endpoint to seed another user's state for the same alert.
    app.dependency_overrides[require_user] = lambda: 8
    response = await client.post(f"/api/alerts/{ids[0]}/state", json={
        "status": "resolved", "note": "other user's decision",
    })
    assert response.status_code == 200
    other = dict(await pool.fetchrow("SELECT * FROM alert_triage_state WHERE user_id=8"))
    app.dependency_overrides[require_user] = lambda: 7

    for status in ("snoozed", "resolved", "open"):
        body = {"alert_ids": ids, "status": status, "note": "reviewed"}
        if status == "snoozed":
            body["snooze_until"] = (datetime.now(UTC) + timedelta(days=1)).isoformat()
        response = await client.post("/api/alerts/state/batch", json=body)
        assert response.status_code == 200
        data = response.json()
        assert data["updated"] == 2
        assert set(data["states"]) == {str(i) for i in ids}
        for state in data["states"].values():
            assert state["status"] == status
            assert state["note"] == "reviewed"
            assert (state["snooze_until"] is not None) == (status == "snoozed")
            assert (state["resolved_at"] is not None) == (status == "resolved")
        rows = await pool.fetch("SELECT * FROM alert_triage_state WHERE user_id=7")
        assert len(rows) == 2 and all(row["status"] == status for row in rows)
        assert dict(await pool.fetchrow("SELECT * FROM alert_triage_state WHERE user_id=8")) == other

    inbox = (await client.get("/api/alerts/inbox")).json()
    attention = (await client.get("/api/alerts/attention")).json()
    assert len(inbox["alerts"]) == 1
    assert inbox["alerts"][0]["member_ids"] == list(reversed(ids))
    assert inbox["alerts"][0]["occurrences"] == 2
    assert inbox["counts"]["needs_action"] == attention["needs_action"] == 1


async def test_alert_batch_unknown_id_writes_nothing(alert_db_client):
    client, pool, ids, _ = alert_db_client
    response = await client.post("/api/alerts/state/batch", json={
        "alert_ids": [ids[0], max(ids) + 1000], "status": "resolved",
    })
    assert response.status_code == 404
    assert await pool.fetchval("SELECT count(*) FROM alert_triage_state") == 0


async def test_alert_batch_transaction_rolls_back_on_mid_batch_failure(alert_db_client, monkeypatch):
    client, pool, ids, _ = alert_db_client
    upsert = alerts._upsert_alert_state

    async def fail_second(connection, user_id, alert_id, *args):
        if alert_id == ids[1]:
            raise RuntimeError("injected write failure")
        return await upsert(connection, user_id, alert_id, *args)

    monkeypatch.setattr(alerts, "_upsert_alert_state", fail_second)
    with pytest.raises(RuntimeError, match="injected write failure"):
        await client.post("/api/alerts/state/batch", json={"alert_ids": ids, "status": "resolved"})
    assert await pool.fetchval("SELECT count(*) FROM alert_triage_state") == 0


async def test_alert_expired_snooze_reopens_group_but_resolved_does_not(alert_db_client):
    client, pool, ids, _ = alert_db_client
    await pool.execute(
        "INSERT INTO alert_triage_state(user_id,alert_id,status,snooze_until) "
        "VALUES(7,$1,'snoozed',now()-interval '1 hour'),(7,$2,'resolved',NULL)", *ids,
    )
    inbox = (await client.get("/api/alerts/inbox")).json()
    assert inbox["alerts"][0]["state"]["status"] == "open"
    assert inbox["counts"]["needs_action"] == 1
    await pool.execute("UPDATE alert_triage_state SET status='resolved' WHERE user_id=7")
    inbox = (await client.get("/api/alerts/inbox")).json()
    assert inbox["alerts"][0]["state"]["status"] == "resolved"
    assert inbox["counts"]["resolved"] == 1
    assert inbox["counts"]["needs_action"] == 0


@pytest.mark.parametrize("body", [
    {"alert_ids": [], "status": "open"},
    {"alert_ids": list(range(201)), "status": "open"},
    {"alert_ids": [1, 1], "status": "open"},
    {"alert_ids": [1], "status": "invalid"},
    {"alert_ids": [1], "status": "open", "note": "x" * 501},
    {"alert_ids": [1], "status": "snoozed"},
    {"alert_ids": [1], "status": "snoozed", "snooze_until": "2020-01-01T00:00:00"},
])
def test_alert_batch_rejects_invalid_body_without_database(body, monkeypatch):
    from api.index import app

    get_pool = AsyncMock()
    monkeypatch.setattr(alerts, "get_db_pool", get_pool)
    app.dependency_overrides[require_user] = lambda: 7
    try:
        response = TestClient(app).post("/api/alerts/state/batch", json=body)
        assert response.status_code == 422
        get_pool.assert_not_called()
    finally:
        app.dependency_overrides.pop(require_user, None)


def test_alert_batch_requires_authentication(monkeypatch):
    from api.index import app

    get_pool = AsyncMock()
    monkeypatch.setattr(alerts, "get_db_pool", get_pool)
    response = TestClient(app).post(
        "/api/alerts/state/batch", json={"alert_ids": [1], "status": "resolved"},
    )
    assert response.status_code == 401
    get_pool.assert_not_called()
