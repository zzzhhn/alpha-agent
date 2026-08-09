"""Refresh dispatch and recommendation publication truthfulness contracts."""
from __future__ import annotations

import json
from datetime import date
from unittest.mock import AsyncMock

import pytest


async def test_refresh_dispatch_propagates_a_unique_request_id(monkeypatch):
    from alpha_agent.api.routes import admin

    captured: dict = {}

    class FakeResponse:
        status_code = 204
        text = ""

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, url, *, json, headers):
            captured.update({"url": url, "json": json, "headers": headers})
            return FakeResponse()

    monkeypatch.setenv("GH_PAT", "test-token")
    monkeypatch.setattr(
        admin, "_cooldown_active", AsyncMock(return_value=(False, None))
    )
    monkeypatch.setattr(admin.httpx, "AsyncClient", lambda **_kwargs: FakeClient())

    response = await admin.trigger_refresh(
        admin.RefreshRequest(job="fast_intraday"), user_id=1
    )

    assert response.ok is True
    assert response.request_id
    assert captured["json"]["inputs"] == {
        "job": "fast_intraday",
        "request_id": response.request_id,
    }


async def test_publish_noop_is_audited_with_request_id(monkeypatch):
    from alpha_agent import ledger
    from alpha_agent.api.routes import cron_routes

    pool = AsyncMock()
    pool.fetchrow.return_value = {
        "id": 38,
        "scheduled_for_date": date(2026, 8, 7),
    }
    monkeypatch.setenv("DATABASE_URL", "postgres://unused")
    monkeypatch.setattr(cron_routes, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(ledger, "record_daily_close", AsyncMock(return_value=None))

    response = await cron_routes.publish_recommendation(request_id="refresh-1")

    assert response["publish_status"] == "no_op_same_market_date"
    assert response["run_id"] == 38
    assert response["request_id"] == "refresh-1"
    audit = json.loads(pool.execute.await_args.args[-1])
    assert audit["publish_status"] == "no_op_same_market_date"
    assert audit["request_id"] == "refresh-1"


async def test_publish_success_and_health_failure_have_distinct_statuses(
    monkeypatch,
):
    from alpha_agent import ledger
    from alpha_agent.api.routes import cron_routes

    monkeypatch.setenv("DATABASE_URL", "postgres://unused")

    for run_status, expected, expected_ok in (
        ("complete", "published", True),
        ("partial", "health_gate_failed", False),
    ):
        pool = AsyncMock()
        pool.fetchrow.return_value = {
            "status": run_status,
            "scheduled_for_date": date(2026, 8, 7),
            "health_json": {"passed": expected_ok},
        }
        monkeypatch.setattr(cron_routes, "get_pool", AsyncMock(return_value=pool))
        monkeypatch.setattr(ledger, "record_daily_close", AsyncMock(return_value=41))

        response = await cron_routes.publish_recommendation(
            request_id=f"refresh-{run_status}"
        )

        assert response["publish_status"] == expected
        assert response["ok"] is expected_ok
        audit = json.loads(pool.execute.await_args.args[-1])
        assert audit["publish_status"] == expected


async def test_publish_exception_writes_failed_audit_then_raises(monkeypatch):
    from alpha_agent import ledger
    from alpha_agent.api.routes import cron_routes

    pool = AsyncMock()
    monkeypatch.setenv("DATABASE_URL", "postgres://unused")
    monkeypatch.setattr(cron_routes, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(
        ledger,
        "record_daily_close",
        AsyncMock(side_effect=ValueError("test failure")),
    )

    with pytest.raises(RuntimeError, match="snapshot publication failed"):
        await cron_routes.publish_recommendation(request_id="refresh-failed")

    audit = json.loads(pool.execute.await_args.args[-1])
    assert audit == {
        "publish_status": "failed",
        "reason": "publish_exception",
        "error_type": "ValueError",
        "request_id": "refresh-failed",
    }
