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
"""
from .factor_db import (
    Base,
    Factor,
    FactorRun,
    decay_alerts,
    delete_factor,
    get_engine,
    get_factor_runs,
    init_schema,
    is_db_configured,
    list_factors,
    record_run,
    upsert_factor,
)

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
