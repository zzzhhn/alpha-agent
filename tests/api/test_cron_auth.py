"""Cron routes fail closed and expose one cheap authenticated smoke path."""
from __future__ import annotations

from pathlib import Path


_ROOT = Path(__file__).resolve().parents[2]


def test_cron_auth_check_rejects_missing_server_secret(client_with_db, monkeypatch):
    monkeypatch.delenv("CRON_SECRET", raising=False)
    response = client_with_db.get("/api/cron/auth_check")
    assert response.status_code == 503
    assert "CRON_SECRET missing" in response.json()["detail"]


def test_cron_auth_check_rejects_bad_bearer(client_with_db, monkeypatch):
    monkeypatch.setenv("CRON_SECRET", "server-secret")
    response = client_with_db.get(
        "/api/cron/auth_check",
        headers={"Authorization": "Bearer wrong-secret"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "invalid cron authorization"


def test_cron_auth_check_accepts_shared_bearer(client_with_db, monkeypatch):
    monkeypatch.setenv("CRON_SECRET", "server-secret")
    response = client_with_db.get(
        "/api/cron/auth_check",
        headers={"Authorization": "Bearer server-secret"},
    )
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_every_cron_operation_declares_authorization_header(client_with_db):
    schema = client_with_db.app.openapi()
    cron_operations = [
        operation
        for path, path_item in schema["paths"].items()
        if path.startswith("/api/cron/")
        for method, operation in path_item.items()
        if method in {"get", "post", "put", "patch", "delete"}
    ]
    assert cron_operations
    for operation in cron_operations:
        header_names = {
            parameter["name"]
            for parameter in operation.get("parameters", [])
            if parameter.get("in") == "header"
        }
        assert "authorization" in header_names, operation["operationId"]


def test_github_cron_callers_send_the_shared_bearer():
    workflows = [
        _ROOT / ".github/workflows/cron-shards.yml",
        _ROOT / ".github/workflows/daily-factor-loop.yml",
        _ROOT / ".github/workflows/propose-job-runner.yml",
    ]
    calls = 0
    for workflow in workflows:
        lines = workflow.read_text().splitlines()
        assert any(
            line.strip() == "CRON_SECRET: ${{ secrets.CRON_SECRET }}"
            for line in lines
        )
        for index, line in enumerate(lines):
            if '"$BACKEND_BASE/api/cron/' not in line:
                continue
            calls += 1
            context = "\n".join(lines[max(0, index - 4) : index])
            assert '-H "Authorization: Bearer $CRON_SECRET"' in context, (
                f"missing cron bearer before {workflow.name}:{index + 1}"
            )
    assert calls >= 17
