"""Persistent account identity and ownership for the simulated paper ledger."""
from __future__ import annotations

import math
from typing import Any

from fastapi import HTTPException


async def resolve_account(
    pool: Any, user_id: int, account_id: int | None = None,
) -> dict[str, Any]:
    """Resolve an owned account. Omitted identity always means the human book.

    Explicit IDs never create anything and deliberately use the same 404 for a
    missing account and another user's account. ``pool`` may be a connection
    inside the caller's short ledger transaction.
    """
    if account_id is not None:
        row = await pool.fetchrow(
            "SELECT * FROM sim_account WHERE id=$1 AND user_id=$2",
            account_id, user_id,
        )
        if row is None:
            raise HTTPException(status_code=404, detail="account not found")
        return dict(row)

    row = await pool.fetchrow(
        "SELECT * FROM sim_account WHERE user_id = $1 AND kind = 'human'", user_id,
    )
    if row is None:
        # A concurrent first visit must return the existing book, not replace
        # its cash, reset cohort, name, or any other durable account state.
        row = await pool.fetchrow(
            "INSERT INTO sim_account (user_id, kind, name) "
            "VALUES ($1, 'human', 'Human account') "
            "ON CONFLICT (user_id, kind) DO UPDATE SET user_id=EXCLUDED.user_id "
            "RETURNING *",
            user_id,
        )
    if row is None:
        raise HTTPException(status_code=500, detail="failed to create sim account")
    return dict(row)


async def create_bot_account(
    pool: Any, user_id: int, name: str, initial_cash: float,
) -> dict[str, Any]:
    """Create the user's one bot book, or return it without changing history."""
    name = name.strip()
    if not name or len(name) > 80:
        raise HTTPException(status_code=400, detail="name must contain 1 to 80 characters")
    if not math.isfinite(initial_cash) or initial_cash <= 0:
        raise HTTPException(status_code=400, detail="initial_cash must be finite and positive")
    row = await pool.fetchrow(
        "INSERT INTO sim_account (user_id, kind, name, initial_cash, cash) "
        "VALUES ($1, 'bot', $2, $3, $3) "
        "ON CONFLICT (user_id, kind) DO UPDATE SET user_id=EXCLUDED.user_id "
        "RETURNING *",
        user_id, name, initial_cash,
    )
    if row is None:
        raise HTTPException(status_code=500, detail="failed to create bot account")
    return dict(row)
