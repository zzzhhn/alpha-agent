"""SQLite-backed registry for accepted factor expressions.

Factors are deduplicated by tree_hash — attempting to add a factor whose
hash already exists returns -1 without raising.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS factors (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    expression      TEXT    NOT NULL,
    hypothesis_name TEXT    NOT NULL,
    rationale       TEXT    NOT NULL,
    metrics         TEXT    NOT NULL,
    tree_hash       TEXT    NOT NULL UNIQUE,
    created_at      TEXT    NOT NULL
);
"""

_INSERT_SQL = """
INSERT INTO factors (expression, hypothesis_name, rationale, metrics, tree_hash, created_at)
VALUES (?, ?, ?, ?, ?, ?)
"""

_SELECT_ALL_SQL = """
SELECT id, expression, hypothesis_name, rationale, metrics, tree_hash, created_at
FROM factors ORDER BY id
"""

_SELECT_BY_ID_SQL = """
SELECT id, expression, hypothesis_name, rationale, metrics, tree_hash, created_at
FROM factors WHERE id = ?
"""

_EXISTS_SQL = "SELECT 1 FROM factors WHERE tree_hash = ? LIMIT 1"
_COUNT_SQL = "SELECT COUNT(*) FROM factors"


@dataclass(frozen=True)
class FactorRecord:
    """An immutable snapshot of a registered factor row."""

    id: int
    expression: str
    hypothesis_name: str
    rationale: str
    metrics: dict
    tree_hash: str
    created_at: str


def _row_to_record(row: tuple) -> FactorRecord:
    """Convert a raw SQLite row tuple into a FactorRecord."""
    factor_id, expression, hypothesis_name, rationale, metrics_json, tree_hash, created_at = row
    return FactorRecord(
        id=factor_id,
        expression=expression,
        hypothesis_name=hypothesis_name,
        rationale=rationale,
        metrics=json.loads(metrics_json),
        tree_hash=tree_hash,
        created_at=created_at,
    )


class FactorRegistry:
    """SQLite-backed registry for accepted factor expressions."""

    def __init__(self, db_path: str | Path = "data/factor_registry.db") -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def add(
        self,
        expression: str,
        hypothesis_name: str,
        rationale: str,
        metrics: dict,
        tree_hash: str,
    ) -> int:
        """Insert a factor and return its row id.

        Returns -1 (without raising) if *tree_hash* already exists.
        """
        if self.exists(tree_hash):
            return -1

        created_at = datetime.now(tz=timezone.utc).isoformat()
        metrics_json = json.dumps(metrics)

        with sqlite3.connect(self._db_path) as conn:
            cursor = conn.execute(
                _INSERT_SQL,
                (expression, hypothesis_name, rationale, metrics_json, tree_hash, created_at),
            )
            conn.commit()
            return cursor.lastrowid  # type: ignore[return-value]

    def exists(self, tree_hash: str) -> bool:
        """Return True if a factor with *tree_hash* is already registered."""
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(_EXISTS_SQL, (tree_hash,)).fetchone()
            return row is not None

    def list_all(self) -> list[FactorRecord]:
        """Return all registered factors ordered by id."""
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(_SELECT_ALL_SQL).fetchall()
            return [_row_to_record(r) for r in rows]

    def get_by_id(self, factor_id: int) -> FactorRecord | None:
        """Return the factor with *factor_id*, or None if not found."""
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(_SELECT_BY_ID_SQL, (factor_id,)).fetchone()
            return _row_to_record(row) if row is not None else None

    def count(self) -> int:
        """Return the total number of registered factors."""
        with sqlite3.connect(self._db_path) as conn:
            result = conn.execute(_COUNT_SQL).fetchone()
            return result[0]

    def _init_db(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(_CREATE_TABLE_SQL)
            conn.commit()
