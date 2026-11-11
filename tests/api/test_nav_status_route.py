"""GET /api/nav/status and GET /api/alerts/attention contracts."""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import asyncpg
import pytest
from fastapi.testclient import TestClient

from alpha_agent.auth.dependencies import require_user


@pytest.fixture(autouse=True)
def _no_github(monkeypatch):
    import alpha_agent.api.routes.nav_status as mod

    monkeypatch.delenv("GH_PAT", raising=False)
    mod._workflow_cache.update(ts=None, state=None)


async def test_nav_status_reports_unknown_without_evidence(client_with_db):
    response = client_with_db.get("/api/nav/status")
    assert response.status_code == 200
    assert response.headers["cache-control"].startswith("public")
    body = response.json()
    assert body["picks"]["state"] == "unknown"
    # Without scheduler access a deliberate pause cannot be proven.
    assert body["evolution"]["state"] == "unknown"
    assert body["evolution"]["pending_reviews"] == 0


async def test_nav_status_reads_snapshot_publish_and_factor_loop(client_with_db, applied_db):
    from alpha_agent.market_session import latest_completed_xnys_session

    expected = latest_completed_xnys_session()
    conn = await asyncpg.connect(applied_db)
    try:
        await conn.execute(
            "INSERT INTO research_run (scheduled_for_date, run_type, status, started_at,"
            " finished_at, health_json) VALUES ($1,'daily_close','complete',now(),now(),$2::jsonb)",
            expected, json.dumps({"passed": True}),
        )
        await conn.execute(
            "INSERT INTO cron_runs (cron_name, started_at, finished_at, ok, error_count, details)"
            " VALUES ('daily_factor_loop', $1, $1, false, 1, '{}'::jsonb)",
            datetime.now(UTC) - timedelta(hours=2),
        )
    finally:
        await conn.close()
    body = client_with_db.get("/api/nav/status").json()
    assert body["picks"]["state"] == "current"
    assert body["picks"]["market_date"] == expected.isoformat()
    assert body["evolution"]["state"] == "failed"
    assert body["evolution"]["last_run_ok"] is False


async def test_disabled_loop_is_reported_as_pause(client_with_db, monkeypatch):
    import alpha_agent.api.routes.nav_status as mod

    monkeypatch.setattr(mod, "_factor_loop_workflow_state",
                        AsyncMock(return_value="disabled_manually"))
    body = client_with_db.get("/api/nav/status").json()
    assert body["evolution"]["state"] == "disabled"


@pytest.fixture
def user_client():
    from api.index import app

    app.dependency_overrides[require_user] = lambda: 7
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(require_user, None)


def _alert(alert_id, ticker, to, minutes):
    return {"id": alert_id, "ticker": ticker, "type": "rating_change",
            "payload": json.dumps({"from": "OW", "to": to, "source_count": 3}),
            "dedup_bucket": alert_id, "created_at": datetime.now(UTC) - timedelta(minutes=minutes)}


def test_attention_matches_inbox_needs_action(user_client, monkeypatch):
    rows = [_alert(1, "SLB", "UW", 5), _alert(2, "AAPL", "BUY", 30), _alert(3, "ZZZ", "OW", 4000)]
    states = [{"alert_id": 2, "status": "resolved", "snooze_until": None,
               "resolved_at": datetime.now(UTC), "note": None, "updated_at": datetime.now(UTC)}]

    def make_pool():
        pool = MagicMock()
        pool.fetch = AsyncMock(side_effect=[
            rows, [{"ticker": "SLB"}], [{"ticker": "AAPL"}],
            [{"ticker": "AAPL", "rank": 3, "run_id": 33, "market_date": "2026-11-09"}], states,
        ])
        return pool

    monkeypatch.setattr("alpha_agent.api.routes.alerts.get_db_pool",
                        AsyncMock(side_effect=lambda: make_pool()))
    inbox = user_client.get("/api/alerts/inbox?limit=50").json()
    attention = user_client.get("/api/alerts/attention")
    assert attention.status_code == 200
    assert attention.headers["cache-control"] == "private, max-age=60"
    body = attention.json()
    assert body["needs_action"] == inbox["counts"]["needs_action"] == 1
    assert body["critical"] == 1
    assert body["window"] == 3


def test_attention_requires_sign_in():
    from api.index import app

    response = TestClient(app).get("/api/alerts/attention")
    assert response.status_code == 401
