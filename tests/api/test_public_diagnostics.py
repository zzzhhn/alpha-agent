from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient


def test_preflight_supported_in_both_entries(monkeypatch):
    from alpha_agent.api.app import create_app

    monkeypatch.setenv("ALPHACORE_AUTH_ENABLED", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    from api.index import app

    for entry in (create_app(), app):
        for method in ("DELETE", "PATCH"):
            result = TestClient(entry).options("/api/watchlist", headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": method,
                "Access-Control-Request-Headers": "Authorization",
            })
            assert result.status_code == 200
            assert method in result.headers["access-control-allow-methods"]


@pytest.mark.asyncio
async def test_edge_error_has_public_reference_and_private_trace(monkeypatch, caplog):
    from alpha_agent.api.routes import basket_edge

    monkeypatch.setattr(basket_edge, "_cache", {"val": None, "ts": None})
    monkeypatch.setattr(basket_edge, "_compute_edge", AsyncMock(side_effect=RuntimeError("fixture-marker")))
    with pytest.raises(HTTPException) as err:
        await basket_edge.picks_edge()
    detail = err.value.detail
    assert detail["code"] == "PICKS_EDGE_UNAVAILABLE"
    assert detail["reference"] in caplog.text
    assert "fixture-marker" in caplog.text
    assert "fixture-marker" not in str(detail)


def test_cold_start_failure_reference_is_shared_across_manifests(monkeypatch, caplog):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    from api import index

    monkeypatch.setattr(index, "_m2_load_errors", {})
    from starlette.datastructures import State
    monkeypatch.setattr(index.app, "state", State({"m2_load_errors": index._m2_load_errors, "router_health": []}))
    index._load("fixture", "alpha_test_missing_router")
    public = TestClient(index.app).get("/api/_debug/load-errors").json()
    reference = public["fixture"]
    assert reference == index.app.state.router_health[0].error
    assert len(reference) == 32 and int(reference, 16) > 0
    assert reference in caplog.text
    assert "alpha_test_missing_router" in caplog.text
