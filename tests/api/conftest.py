"""FastAPI TestClient + DB fixture for API route tests.

Re-exports the pytest-postgresql fixtures from tests.storage.conftest so
any conftest.py only needs to import from one place.  Pattern mirrors
tests/cron/conftest.py.

Pool singleton note: alpha_agent.storage.postgres._pool is module-level.
We close + reset it in the client_with_db teardown so each test gets a
fresh pool pointing at the test DB.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from alpha_agent.api.app import create_app

# Re-export storage fixtures so pytest discovers them here.
from tests.storage.conftest import (  # noqa: F401
    applied_db,
    postgresql,
    postgresql_proc,
    test_db_url,
)


@pytest.fixture
def client_with_db(applied_db, monkeypatch):  # noqa: F811
    """TestClient backed by a fresh test DB.

    Monkeypatches DATABASE_URL before create_app() so get_db_pool() picks
    up the correct DSN.  Resets the pool singleton after each test so the
    next test's create_app() starts clean.
    """
    monkeypatch.setenv("DATABASE_URL", applied_db)

    # Reset module-level singleton so this test's DSN is used.
    import alpha_agent.storage.postgres as _pg
    _pg._pool = None
    _pg._pool_dsn = None

    app = create_app()
    client = TestClient(app, raise_server_exceptions=True)
    yield client

    # Teardown: synchronously reset the module-level singleton so the next
    # test starts with a clean slate.  We cannot safely run an async close
    # here (the event loop may already be in a post-test state), so we
    # just discard the reference — asyncpg pools are GC-safe to drop.
    _pg._pool = None
    _pg._pool_dsn = None
