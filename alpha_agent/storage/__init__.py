"""Persistent storage for factor metadata + run history.

T4.1 of the v4 audit. Backs the Factor Zoo with a real database (Neon
Postgres in prod, sqlite for local dev) so:

  1. Factors persist across browser sessions (localStorage was per-user-
     per-browser; lost on cache clear or new device).
  2. Run history is preserved — every backtest invocation appends a
     FactorRun, enabling decay-alert detection (rolling IC vs baseline)
     and walk-forward stability analysis post-hoc.
  3. Multi-agent / regime / genetic search (T4.3-T4.5) have a fitness
     store to query.

NOTE (M2 fix): `factor_db.py` imports SQLAlchemy at module load. SQLAlchemy
is not in the Vercel runtime bundle (heavy + only needed for v3 factor zoo
admin paths, not M2 read paths). Eagerly re-exporting from `factor_db` here
made `from alpha_agent.storage.postgres import get_pool` (M2's asyncpg path)
trigger SQLAlchemy import → ModuleNotFoundError → all 4 M2 routers silently
failed. Fix: lazy `__getattr__` so callers explicitly importing factor_db
symbols still work, but `alpha_agent.storage.postgres` is loadable on its own.
"""
from __future__ import annotations

from typing import Any

__all__ = [
    "Base",
    "Factor",
    "FactorRun",
    "get_engine",
    "init_schema",
    "upsert_factor",
    "record_run",
    "list_factors",
    "get_factor_runs",
    "delete_factor",
    "decay_alerts",
    "is_db_configured",
]


def __getattr__(name: str) -> Any:
    """PEP 562 lazy re-export: only import factor_db when its symbols
    are actually accessed (not on every `import alpha_agent.storage`)."""
    if name in __all__:
        from . import factor_db
        return getattr(factor_db, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
