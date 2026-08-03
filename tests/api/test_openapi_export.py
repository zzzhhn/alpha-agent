"""OpenAPI schema drift gate.

Fails if the committed openapi.snapshot.json diverges from the live schema
produced by create_app(). Run `make openapi-export` to regenerate when an
intentional API change is made.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient


def test_openapi_export_matches_disk():
    """Verify openapi.snapshot.json is up to date with the backend OpenAPI.

    Run `make openapi-export` to regenerate when intentionally changing API."""
    from alpha_agent.api.app import create_app

    spec = create_app().openapi()

    expected_path = Path(__file__).parent.parent.parent / "openapi.snapshot.json"
    if not expected_path.exists():
        # First-run: write snapshot and fail so the reviewer can inspect it.
        expected_path.write_text(json.dumps(spec, indent=2, sort_keys=True))
        raise AssertionError(
            f"Wrote initial snapshot to {expected_path}; review and re-run"
        )

    on_disk = json.loads(expected_path.read_text())
    if json.dumps(on_disk, sort_keys=True) != json.dumps(spec, sort_keys=True):
        raise AssertionError(
            "OpenAPI schema drift detected. Run `make openapi-export` to update."
        )


def test_openapi_is_available_through_frontend_api_proxy_path():
    from alpha_agent.api.app import create_app

    response = TestClient(create_app()).get("/api/openapi.json")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    spec = response.json()
    assert "/api/picks/lean" in spec["paths"]
    assert "/api/l2/summary" in spec["paths"]
