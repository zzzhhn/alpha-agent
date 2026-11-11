"""Production serves api/index.py, not create_app().

The two keep separate router manifests. A router registered only in
create_app() passes every create_app-based test yet 404s in production
(2026-11-11: /api/nav/status). Keep the two lists identical.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _app_routers() -> set[str]:
    source = (ROOT / "alpha_agent/api/app.py").read_text()
    return set(re.findall(r"from alpha_agent\.api\.routes\.(\w+) import router", source))


def _serverless_routers() -> set[str]:
    source = (ROOT / "api/index.py").read_text()
    return set(re.findall(r'_load\(\s*"\w+",\s*"alpha_agent\.api\.routes\.(\w+)"\)', source))


def test_serverless_entry_registers_every_app_router():
    missing = _app_routers() - _serverless_routers()
    # factors_db requires SQLAlchemy, which the Vercel bundle omits on purpose.
    assert missing <= {"factors_db"}, f"routers missing from api/index.py: {sorted(missing)}"


def test_nav_status_route_is_served_by_production_entry():
    from fastapi.testclient import TestClient

    from api.index import app

    loaded = {entry.name for entry in app.state.router_health if entry.loaded}
    assert "nav_status" in loaded
    paths = set(app.openapi()["paths"])
    assert "/api/nav/status" in paths
    assert "/api/alerts/attention" in paths
    assert TestClient(app).get("/api/alerts/attention").status_code == 401
