"""Postgres test fixture using pytest-postgresql.

Spins up a fresh Postgres process per test session; gives us
a real DB without external dependencies. Each test gets a
clean schema via auto-applied migrations.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from pytest_postgresql import factories

postgresql_proc = factories.postgresql_proc(port=None, unixsocketdir="/tmp")
postgresql = factories.postgresql("postgresql_proc")


@pytest.fixture
def test_db_url(postgresql) -> str:
    """asyncpg-compatible DSN."""
    info = postgresql.info
    return f"postgres://{info.user}@/{info.dbname}?host={info.host}&port={info.port}"


@pytest_asyncio.fixture
async def applied_db(test_db_url):
    """Test DB with all migrations applied."""
    from alpha_agent.storage.migrations.runner import apply_migrations
    await apply_migrations(test_db_url)
    return test_db_url
