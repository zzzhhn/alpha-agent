"""Phase 3c factor-lab endpoint tests. Reuses the admin-auth fixture pattern
from tests/api/test_evolution_approval.py."""
import time

import pytest
from jose import jwt

_SECRET = "test-secret-not-real-0123456789"


def _auth(sub: str = "1") -> dict:
    now = int(time.time())
    tok = jwt.encode({"sub": sub, "iat": now, "exp": now + 3600}, _SECRET, algorithm="HS256")
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture
def authed_client(client_with_db, monkeypatch):
    monkeypatch.setenv("NEXTAUTH_SECRET", _SECRET)
    return client_with_db


def test_get_diagnostic_returns_current_expression(client_with_db):
    r = client_with_db.get("/api/factor-lab/diagnostic")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "current_expression" in body
    assert "weak_signal" in body
    assert "symptom_summary" in body


def test_post_propose_requires_admin_auth(client_with_db):
    """Unauthed POST returns 401."""
    r = client_with_db.post("/api/factor-lab/propose", json={"n": 3})
    assert r.status_code == 401


def test_post_propose_returns_dormant_on_starved_history(authed_client):
    """No daily_prices history (or below threshold) -> dormant=True,
    proposed=0, evaluated=0. The cost-guard fires BEFORE the BYOK LLM call,
    so no LLM headers are needed for this scenario."""
    r = authed_client.post(
        "/api/factor-lab/propose", headers=_auth(),
        json={"n": 3},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # The endpoint is now job-shaped: a dormant short-circuit completes inline
    # and nests the result under inline_result (the LLM path returns
    # {job_id, status: "queued"} instead).
    assert body["status"] == "done"
    result = body["inline_result"]
    assert result["dormant"] is True
    assert result["proposed"] == 0
    assert result["evaluated"] == 0
