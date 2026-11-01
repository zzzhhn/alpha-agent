"""Read-only admission check for scheduled ingestion, not a billing estimator."""
from __future__ import annotations

import os


def storage_admission(used_bytes: int, budget_mib: int) -> dict:
    """Keep 20% headroom inside an operator budget (not the provider quota)."""
    if budget_mib <= 0 or used_bytes < 0:
        raise ValueError("Storage budget must be positive and usage nonnegative")
    budget_bytes = budget_mib * 1024 * 1024
    allowed = used_bytes < budget_bytes * 0.8
    return {
        "allow_writes": allowed,
        "reason": "within_storage_budget" if allowed else "storage_headroom_low",
        "database_bytes": used_bytes,
        "budget_bytes": budget_bytes,
        "stop_at_fraction": 0.8,
        "scope": "current_database_physical_size",
    }


async def read_capacity(pool) -> dict:
    # Intentionally below the observed 1 GiB Neon branch limit. This leaves
    # room for indexes, WAL, other branches and maintenance. No deletion here.
    budget_mib = int(os.environ.get("DB_STORAGE_BUDGET_MIB", "512"))
    used = await pool.fetchval(
        "SELECT pg_database_size(current_database())", timeout=5,
    )
    return storage_admission(int(used), budget_mib)
