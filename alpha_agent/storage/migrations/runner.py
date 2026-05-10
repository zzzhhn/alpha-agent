"""Apply versioned SQL migrations to a Postgres DB.

Idempotent: re-running is a no-op (tracked in schema_migrations).
Discovery: any file matching V<NUM>__<name>.sql under this directory.
Order: lexicographic by filename — keep V001/V002/... padding consistent.
"""
from __future__ import annotations

import re
from pathlib import Path

import asyncpg

_MIGRATIONS_DIR = Path(__file__).parent
_VERSION_RE = re.compile(r"^V(\d+)__.+\.sql$")


def _discover() -> list[tuple[str, Path]]:
    files = sorted(_MIGRATIONS_DIR.glob("V*__*.sql"))
    out = []
    for f in files:
        m = _VERSION_RE.match(f.name)
        if m:
            out.append((f.stem, f))
    return out


async def apply_migrations(dsn: str) -> list[str]:
    """Apply all pending migrations to dsn. Returns list of applied versions."""
    conn = await asyncpg.connect(dsn)
    applied: list[str] = []
    try:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ DEFAULT now()
            )
        """)
        rows = await conn.fetch("SELECT version FROM schema_migrations")
        already = {r["version"] for r in rows}
        for version, path in _discover():
            if version in already:
                continue
            sql = path.read_text(encoding="utf-8")
            async with conn.transaction():
                await conn.execute(sql)
                await conn.execute(
                    "INSERT INTO schema_migrations (version) VALUES ($1)", version
                )
            applied.append(version)
    finally:
        await conn.close()
    return applied
