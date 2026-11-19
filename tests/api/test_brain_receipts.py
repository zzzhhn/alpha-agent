"""Exercise BRAIN HTTP via MockTransport and Postgres via disposable fixtures."""

import asyncio
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from unittest.mock import AsyncMock

import asyncpg
import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient

from alpha_agent.api.dependencies import get_db_pool
from alpha_agent.api.routes import brain_routes, serverless
from alpha_agent.auth.dependencies import require_user
from alpha_agent.brain import client as brain_client, store, vault


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(brain_routes.router)
    app.include_router(serverless.router)
    app.dependency_overrides[require_user] = lambda: 9
    app.dependency_overrides[get_db_pool] = lambda: object()
    with TestClient(app) as client:
        yield client


@pytest.mark.parametrize(("path", "query", "key"), [
    ("/api/brain/alphas", "query_brain_alphas", "alphas"),
    ("/api/brain/runs", "list_brain_runs", "runs"),
])
def test_brain_list_failure_is_not_an_empty_success(client, monkeypatch, path, query, key):
    mocked = AsyncMock(side_effect=RuntimeError("internal-database-details"))
    monkeypatch.setattr(store, query, mocked)
    response = client.get(path)
    assert response.status_code == 503
    assert "internal-database-details" not in response.text

    mocked.side_effect = None
    mocked.return_value = {key: [], "total": 0}
    response = client.get(path)
    assert response.status_code == 200
    assert response.json() == {key: [], "total": 0}


@pytest.mark.parametrize("path", ["positions", "risk"])
@pytest.mark.parametrize("ml_available", [True, False])
def test_legacy_portfolio_responds_gone_instead_of_demo_data(
    client, monkeypatch, path, ml_available,
):
    monkeypatch.setattr(serverless, "_check_ml", lambda: ml_available)
    response = client.get(f"/api/v1/portfolio/{path}")
    assert response.status_code == 410
    assert "demo" in response.json()["detail"]


class MockBrain:
    def __init__(self):
        self.submit_status = 201
        self.alpha_status = "UNSUBMITTED"
        self.auth_status = 201
        self.submit_error = None
        self.submit_hook = None
        self.retry_after = "7.2"
        self.calls = []

    async def handle(self, request):
        self.calls.append((request.method, request.url.path))
        if request.url.path == "/authentication":
            return httpx.Response(self.auth_status, headers={"Retry-After": self.retry_after})
        if request.url.path == "/alphas/alpha_stub/submit" and request.method == "POST":
            if self.submit_hook is not None:
                await self.submit_hook()
            if self.submit_error:
                raise self.submit_error("private network detail", request=request)
            return httpx.Response(
                self.submit_status, text="private upstream detail",
                headers={"Retry-After": self.retry_after, "Location": "/unexpected-redirect"},
            )
        if request.url.path == "/alphas/alpha_stub" and request.method == "GET":
            return httpx.Response(200, json={"id": "alpha_stub", "status": self.alpha_status})
        raise AssertionError(f"unexpected upstream call: {request.method} {request.url.path}")

    def submit_count(self):
        return self.calls.count(("POST", "/alphas/alpha_stub/submit"))


@pytest_asyncio.fixture
async def submission_env(applied_db, monkeypatch):
    pool = await asyncpg.create_pool(applied_db, min_size=1, max_size=3)
    app = FastAPI()
    app.include_router(brain_routes.router)
    app.dependency_overrides[require_user] = lambda: 9
    app.dependency_overrides[get_db_pool] = lambda: pool
    monkeypatch.setattr(vault, "load_brain_credentials", AsyncMock(return_value=("synthetic", "synthetic")))
    upstream = MockBrain()
    original_client = brain_client.BrainClient
    monkeypatch.setattr(brain_client, "BrainClient", lambda *_args: original_client(
        "synthetic", "synthetic", client=httpx.AsyncClient(
            transport=httpx.MockTransport(upstream.handle),
            base_url="https://brain.example.invalid",
            follow_redirects=True,
        ),
    ))
    row_id = await pool.fetchval(
        "INSERT INTO brain_alphas (user_id, expression, alpha_id, outcome) "
        "VALUES (9, 'rank(close)', 'alpha_stub', 'passed') RETURNING id",
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://testserver",
    ) as client:
        yield client, upstream, pool, row_id
    await pool.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(("http_code", "expected", "confirmed"), [
    (200, "submitted", True),
    (201, "submitted", True),
    (400, "submit_rejected", False),
    (422, "submit_rejected", False),
    (302, "submit_unknown", False),
    (408, "submit_unknown", False),
    (409, "submit_unknown", False),
    (500, "submit_unknown", False),
    (503, "submit_unknown", False),
])
async def test_submit_receipt_and_timestamp(submission_env, http_code, expected, confirmed):
    client, upstream, pool, row_id = submission_env
    upstream.submit_status = http_code
    resp = await client.post(f"/api/brain/alphas/{row_id}/submit")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "ok": confirmed, "brain_status": expected, "alpha_id": "alpha_stub", "retry_after_sec": None,
    }
    stored = await store.get_brain_alpha(pool, 9, row_id)
    assert stored["brain_status"] == expected
    assert bool(stored["submitted_at"]) == confirmed
    assert len(upstream.calls) == 2
    if expected != "submit_rejected":
        assert (await client.post(f"/api/brain/alphas/{row_id}/submit")).json() == resp.json()
        assert upstream.submit_count() == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [httpx.ReadTimeout, httpx.ConnectError])
async def test_unknown_transport_blocks_resubmission_until_positive_readback(submission_env, failure):
    client, upstream, pool, row_id = submission_env
    upstream.submit_error = failure
    route = f"/api/brain/alphas/{row_id}"
    assert (await client.post(f"{route}/submit")).json()["brain_status"] == "submit_unknown"
    assert (await client.post(f"{route}/reconcile-submission")).json()["brain_status"] == "submit_unknown"
    assert (await client.post(f"{route}/submit")).json()["brain_status"] == "submit_unknown"
    assert upstream.submit_count() == 1

    upstream.alpha_status = "ACTIVE"
    assert (await client.post(f"{route}/reconcile-submission")).json()["brain_status"] == "active"
    assert upstream.submit_count() == 1
    stored = await store.get_brain_alpha(pool, 9, row_id)
    assert stored["brain_status"] == "active"
    assert stored["submitted_at"] is not None


@pytest.mark.asyncio
async def test_cooldown_and_no_automatic_retry(submission_env):
    client, upstream, pool, row_id = submission_env
    upstream.submit_status = 429
    route = f"/api/brain/alphas/{row_id}/submit"
    first = await client.post(route)
    assert first.status_code == 429
    assert first.headers["Retry-After"] == "8"
    assert first.json()["brain_status"] == "submit_rate_limited"
    stored = await store.get_brain_alpha(pool, 9, row_id)
    assert stored["submitted_at"] is None
    assert stored["submit_retry_at"] is not None
    second = await client.post(route)
    assert second.status_code == 429
    assert upstream.submit_count() == 1
    await pool.execute("UPDATE brain_alphas SET submit_retry_at=now() WHERE id=$1", row_id)
    assert upstream.submit_count() == 1
    upstream.submit_status = 201
    assert (await client.post(route)).json()["ok"] is True
    assert upstream.submit_count() == 2
    stored = await store.get_brain_alpha(pool, 9, row_id)
    assert stored["submit_retry_at"] is None


@pytest.mark.asyncio
async def test_authentication_rate_limit_is_not_a_submission_attempt(submission_env):
    client, upstream, pool, row_id = submission_env
    upstream.auth_status = 429
    upstream.retry_after = format_datetime(datetime.now(timezone.utc) + timedelta(minutes=1))
    response = await client.post(f"/api/brain/alphas/{row_id}/submit")
    assert response.status_code == 429
    assert 50 <= int(response.headers["Retry-After"]) <= 60
    assert upstream.submit_count() == 0
    stored = await store.get_brain_alpha(pool, 9, row_id)
    assert stored["brain_status"] is None


@pytest.mark.asyncio
async def test_two_concurrent_requests_can_send_only_one_post(submission_env):
    client, upstream, pool, row_id = submission_env
    started, release = asyncio.Event(), asyncio.Event()

    async def hold_first_post():
        started.set()
        await release.wait()

    upstream.submit_hook = hold_first_post
    route = f"/api/brain/alphas/{row_id}/submit"
    first = asyncio.create_task(client.post(route))
    try:
        await asyncio.wait_for(started.wait(), timeout=3)
        second = await client.post(route)
        assert second.json()["brain_status"] == "submit_unknown"
        assert upstream.submit_count() == 1
    finally:
        release.set()
        result = await first
    assert result.json()["brain_status"] == "submitted"
    assert upstream.submit_count() == 1


@pytest.mark.asyncio
async def test_failed_receipt_write_does_not_release_post_claim(submission_env, monkeypatch):
    client, upstream, _, row_id = submission_env
    monkeypatch.setattr(store, "finish_brain_submission", AsyncMock(side_effect=RuntimeError("write failed")))
    route = f"/api/brain/alphas/{row_id}/submit"
    assert (await client.post(route)).status_code == 500
    assert (await client.post(route)).json()["brain_status"] == "submit_unknown"
    assert upstream.submit_count() == 1


@pytest.mark.asyncio
async def test_historical_failure_is_unconfirmed_not_a_submitted_filter_match(submission_env):
    client, upstream, pool, row_id = submission_env
    old_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    await pool.execute(
        "UPDATE brain_alphas SET submitted_at=$2, brain_status='submit_rejected' WHERE id=$1",
        row_id, old_time,
    )
    assert (await client.get("/api/brain/alphas?submitted=true")).json()["total"] == 0
    assert (await client.get("/api/brain/alphas?submitted=false")).json()["total"] == 1
    assert (await client.post(f"/api/brain/alphas/{row_id}/submit")).json()["brain_status"] == "submit_unknown"
    assert (await client.post(f"/api/brain/alphas/{row_id}/reconcile-submission")).json()["brain_status"] == "submit_unknown"
    assert upstream.submit_count() == 0
    stored = await store.get_brain_alpha(pool, 9, row_id)
    assert stored["brain_status"] == "submit_rejected"
    assert datetime.fromisoformat(stored["submitted_at"]) == old_time


@pytest.mark.asyncio
async def test_submission_and_reconciliation_reject_foreign_row_without_upstream_call(submission_env):
    client, upstream, pool, row_id = submission_env
    await pool.execute("UPDATE brain_alphas SET user_id=10 WHERE id=$1", row_id)
    for action in ("submit", "reconcile-submission"):
        assert (await client.post(f"/api/brain/alphas/{row_id}/{action}")).status_code == 404
    assert upstream.calls == []
