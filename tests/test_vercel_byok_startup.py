"""The production entrypoint must honor BYOK-only mode without hiding real failures."""

import runpy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from alpha_agent.config import Settings


@pytest.mark.parametrize("require_byok", ["true", "false"])
def test_vercel_startup_distinguishes_byok_only_from_missing_system_key(monkeypatch, require_byok):
    monkeypatch.setenv("ALPHACORE_REQUIRE_BYOK", require_byok)
    # Empty (not absent) also prevents legacy dotenv loaders from restoring a DSN.
    monkeypatch.setenv("DATABASE_URL", "")
    settings = Settings(llm_provider="kimi", kimi_api_key="", _env_file=None)
    monkeypatch.setattr("alpha_agent.config.get_settings", lambda: settings)

    entrypoint = Path(__file__).resolve().parents[1] / "api" / "index.py"
    app = runpy.run_path(str(entrypoint))["app"]

    assert app.state.llm is None
    if require_byok == "true":
        assert app.state.llm_init_error is None
    else:
        assert "KIMI_API_KEY" in app.state.llm_init_error
    # Exercise HTTP behavior: newer FastAPI versions keep included routers lazy.
    client = TestClient(app)
    assert client.get("/api/_health/routers").status_code == 200
    assert client.post("/api/v1/alpha/translate", json={"text": "test"}).status_code == 401
