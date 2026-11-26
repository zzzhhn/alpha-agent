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

    monkeypatch.setenv("NEXTAUTH_SECRET", "alert-group-fixture-secret")
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


async def test_alert_group_page_keeps_members_outside_latest_50_raw_alerts(alert_db_client):
    client, pool, _, _ = alert_db_client
    await pool.execute("DELETE FROM alert_queue")
    old, new = datetime(2026, 7, 14, 13, tzinfo=UTC), datetime(2026, 7, 14, 16, tzinfo=UTC)
    oldest = await pool.fetchval(
        "INSERT INTO alert_queue(ticker,type,dedup_bucket,created_at) "
        "VALUES('AAPL','rating_change',1,$1) RETURNING id", old,
    )
    await pool.execute(
        "INSERT INTO alert_queue(ticker,type,dedup_bucket,created_at) "
        "SELECT 'X' || i,'news_velocity',1,$1::timestamptz + i * interval '1 minute' "
        "FROM generate_series(1,49) i", old,
    )
    latest = await pool.fetchval(
        "INSERT INTO alert_queue(ticker,type,dedup_bucket,created_at) "
        "VALUES('AAPL','rating_change',2,$1) RETURNING id", new,
    )
    response = await client.get("/api/alerts/inbox?limit=50")
    assert response.status_code == 200, response.text
    body = response.json()
    group = next(item for item in body["alerts"] if item["ticker"] == "AAPL")
    assert group["member_ids"] == [latest, oldest]
    assert group["first_seen_at"] == old.isoformat()
    assert group["last_seen_at"] == new.isoformat()
    assert group["occurrences"] == 2


async def test_group_actions_use_the_read_members_and_restore_each_users_prior_state(alert_db_client):
    client, pool, _, app = alert_db_client
    await pool.execute("DELETE FROM alert_queue")

    async def insert(connection, bucket, iso):
        return await connection.fetchval(
            "INSERT INTO alert_queue(ticker,type,payload,dedup_bucket,created_at) "
            "VALUES('AAPL','rating_change','{\"to\":\"UW\"}',$1,$2) RETURNING id",
            bucket, datetime.fromisoformat(iso),
        )

    previous_day = await insert(pool, 1, "2026-11-11T04:59:00+00:00")
    first = await insert(pool, 2, "2026-11-11T05:01:00+00:00")
    last = await insert(pool, 3, "2026-11-11T05:15:00+00:00")
    await pool.execute(
        "INSERT INTO alert_triage_state(user_id,alert_id,status,note,resolved_at) "
        "VALUES(7,$1,'resolved','previous decision',now()),(8,$2,'resolved','other user',now())",
        first, last,
    )
    baseline = dict(await pool.fetchrow(
        "SELECT status,note,resolved_at FROM alert_triage_state WHERE user_id=7 AND alert_id=$1", first,
    ))
    other = dict(await pool.fetchrow("SELECT * FROM alert_triage_state WHERE user_id=8"))
    async with pool.acquire() as writer, writer.transaction():
        # Received an id before the read, but became visible only afterwards.
        late = await insert(writer, 4, "2026-11-11T05:03:00+00:00")
        response = await client.get("/api/alerts/inbox?limit=1")
        assert response.status_code == 200
        assert response.headers["Cache-Control"] == "private, no-store"
        seen = response.json()
        group = seen["alerts"][0]
        assert group["member_ids"] == [last, first]
        assert seen["next_offset"] == 1
        prior_page = (await client.get("/api/alerts/inbox?limit=1&offset=1")).json()
        assert prior_page["alerts"][0]["member_ids"] == [previous_day]
        assert prior_page["alerts"][0]["group_id"] != group["group_id"]
        assert prior_page["next_offset"] is None

    token = group["group_token"]
    app.dependency_overrides[require_user] = lambda: 8
    body = {"group_token": token, "status": "resolved"}
    assert (await client.post("/api/alerts/state/group", json=body)).status_code == 403
    app.dependency_overrides[require_user] = lambda: 7
    assert (await client.post("/api/alerts/state/group", json=body | {"group_token": "fake"})).status_code == 422
    pending = (await client.post("/api/alerts/state/group", json=body)).json()
    assert pending["updated"] == 2 and pending["state"]["status"] == "resolved"
    rows = await pool.fetch("SELECT alert_id,status FROM alert_triage_state WHERE user_id=7 ORDER BY alert_id")
    assert [tuple(row) for row in rows] == [(first, "resolved"), (last, "resolved")]
    refreshed = (await client.get("/api/alerts/inbox?limit=1")).json()["alerts"][0]
    assert refreshed["member_ids"] == [last, late, first]
    assert refreshed["state"]["status"] == "open"

    undo = {"group_token": token, "undo_token": pending["undo_token"]}
    assert (await client.post(
        "/api/alerts/state/group/undo", json=undo | {"group_token": refreshed["group_token"]},
    )).status_code == 422
    app.dependency_overrides[require_user] = lambda: 8
    assert (await client.post("/api/alerts/state/group/undo", json=undo)).status_code == 403
    app.dependency_overrides[require_user] = lambda: 7
    response = await client.post("/api/alerts/state/group/undo", json=undo)
    assert response.status_code == 200 and response.json()["state"]["status"] == "open"
    rows = await pool.fetch("SELECT alert_id,status,note,resolved_at FROM alert_triage_state WHERE user_id=7")
    assert [dict(row) for row in rows] == [{"alert_id": first, **baseline}]
    assert dict(await pool.fetchrow("SELECT * FROM alert_triage_state WHERE user_id=8")) == other
    assert (await client.post("/api/alerts/state/group/undo", json=undo)).status_code == 409


async def test_group_receipt_does_not_undo_a_newer_legacy_decision(alert_db_client):
    client, pool, ids, _ = alert_db_client
    group = (await client.get("/api/alerts/inbox")).json()["alerts"][0]
    token = group["group_token"]
    applied = (await client.post("/api/alerts/state/group", json={
        "group_token": token, "status": "resolved",
    })).json()
    response = await client.post(f"/api/alerts/{ids[0]}/state", json={"status": "open", "note": "new decision"})
    assert response.status_code == 200
    response = await client.post("/api/alerts/state/group/undo", json={
        "group_token": token, "undo_token": applied["undo_token"],
    })
    assert response.status_code == 409
    rows = await pool.fetch("SELECT alert_id,status,note FROM alert_triage_state WHERE user_id=7 ORDER BY alert_id")
    assert [tuple(row) for row in rows] == [(ids[0], "open", "new decision"), (ids[1], "resolved", None)]


async def test_group_action_handles_more_members_than_legacy_batch_limit(alert_db_client):
    client, pool, _, _ = alert_db_client
    await pool.execute(
        "INSERT INTO alert_queue(ticker,type,dedup_bucket,created_at) "
        "SELECT 'LARGE','news_velocity',i,'2026-11-11T18:00:00+00:00'::timestamptz "
        "FROM generate_series(1,201) i",
    )
    inbox = (await client.get("/api/alerts/inbox")).json()
    group = next(item for item in inbox["alerts"] if item["ticker"] == "LARGE")
    assert group["occurrences"] == len(group["member_ids"]) == 201
    response = await client.post("/api/alerts/state/group", json={
        "group_token": group["group_token"], "status": "resolved",
    })
    assert response.status_code == 200 and response.json()["updated"] == 201
    assert await pool.fetchval(
        "SELECT count(*) FROM alert_triage_state WHERE user_id=7 AND status='resolved'",
    ) == 201
