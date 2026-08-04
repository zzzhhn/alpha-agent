from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from alpha_agent.auth.dependencies import require_user


@pytest.fixture
def client():
    from api.index import app

    app.dependency_overrides[require_user] = lambda: 7
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(require_user, None)


def _alert_row():
    return {
        "id": 91,
        "ticker": "SLB",
        "type": "rating_change",
        "payload": '{"from":"OW","to":"UW","source_count":3}',
        "dedup_bucket": 123,
        "created_at": datetime.now(UTC) - timedelta(minutes=5),
    }


def test_inbox_enriches_alert_with_user_decision_context(client, monkeypatch):
    pool = MagicMock()
    pool.fetch = AsyncMock(side_effect=[
        [_alert_row()],
        [{"ticker": "SLB"}],
        [{"ticker": "SLB"}],
        [{"ticker": "SLB", "rank": 3, "run_id": 33, "market_date": "2026-08-01"}],
        [],
    ])
    monkeypatch.setattr(
        "alpha_agent.api.routes.alerts.get_db_pool",
        AsyncMock(return_value=pool),
    )

    response = client.get("/api/alerts/inbox?limit=50")

    assert response.status_code == 200
    body = response.json()
    alert = body["alerts"][0]
    assert alert["severity"] == "critical"
    assert alert["relevance"] == "position"
    assert alert["triage_score"] == 100
    assert alert["context"]["recommendation_run_id"] == 33
    assert body["counts"]["needs_action"] == 1
    assert body["source_status"] == "fresh"


def test_state_endpoint_persists_resolved_decision(client, monkeypatch):
    now = datetime.now(UTC)
    pool = MagicMock()
    pool.fetchval = AsyncMock(return_value=True)
    pool.fetchrow = AsyncMock(return_value={
        "status": "resolved",
        "snooze_until": None,
        "resolved_at": now,
        "note": "reviewed",
        "updated_at": now,
    })
    monkeypatch.setattr(
        "alpha_agent.api.routes.alerts.get_db_pool",
        AsyncMock(return_value=pool),
    )

    response = client.post(
        "/api/alerts/91/state",
        json={"status": "resolved", "note": "reviewed"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "resolved"
    assert pool.fetchrow.call_args.args[3] == "resolved"


def test_snooze_requires_future_time(client, monkeypatch):
    monkeypatch.setattr(
        "alpha_agent.api.routes.alerts.get_db_pool",
        AsyncMock(return_value=MagicMock()),
    )
    response = client.post(
        "/api/alerts/91/state",
        json={
            "status": "snoozed",
            "snooze_until": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
        },
    )

    assert response.status_code == 422
