"""B9 (2026-05-19) — append-only audit log for user config edits.

Drives the diff card + 1-click rollback UI in /settings. Source:
synthesizer T9 + Douyin v#2 TraderCore "尺子不是修理工" — every
recommended setting change must be reversible and visibly diff'd
before committing in the user's head.

Schema (V009):
  id          : BIGSERIAL PK
  user_id     : owner
  field       : dotted path (e.g. byok.provider, weights.factor)
  old_value   : text (NULL for first write of a field)
  new_value   : text
  changed_at  : auto-now
  source      : 'manual' | 'rollback' | 'system' (for future cron-driven
                weight auto-adjusts)
  rollback_of : FK → config_change_log.id if this row undoes a prior change

Security: secret material (api_key ciphertext + nonce) is intentionally
out of scope. record_change() callers in user.save_byok hook only log
the non-secret coordinates (provider / model / base_url). Rollback can
re-apply those without touching the ciphertext.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any


# Fields whose old_value can be safely re-applied via the rollback
# endpoint. Anything outside this set returns 400 from POST /rollback.
ROLLBACK_SAFE_FIELDS: frozenset[str] = frozenset({
    "byok.provider",
    "byok.model",
    "byok.base_url",
    # Reserved for B9.1 (signal weight overrides UI):
    # "weights.factor", "weights.technicals", ...
})


async def record_change(
    pool,
    user_id: int,
    field: str,
    old_value: Any | None,
    new_value: Any | None,
    source: str = "manual",
    rollback_of: int | None = None,
) -> int:
    """Append a change_log row. Returns the new row id.

    Values are str-coerced; pass JSON-stringified payloads for complex
    types if the caller needs to round-trip them. None becomes SQL NULL.
    Failures log + raise — the caller (save_byok) wraps in try/except
    so a log-write failure doesn't break the underlying setting write.
    """
    def _to_text(v: Any | None) -> str | None:
        if v is None:
            return None
        return str(v)

    row = await pool.fetchrow(
        "INSERT INTO config_change_log "
        "  (user_id, field, old_value, new_value, source, rollback_of) "
        "VALUES ($1, $2, $3, $4, $5, $6) "
        "RETURNING id",
        user_id, field, _to_text(old_value), _to_text(new_value),
        source, rollback_of,
    )
    return int(row["id"])


async def fetch_history(
    pool, user_id: int, limit: int = 50,
) -> list[dict[str, Any]]:
    """Recent changes for one user, newest first."""
    rows = await pool.fetch(
        "SELECT id, field, old_value, new_value, changed_at, source, "
        "       rollback_of "
        "FROM config_change_log "
        "WHERE user_id = $1 "
        "ORDER BY changed_at DESC, id DESC "
        "LIMIT $2",
        user_id, int(limit),
    )
    return [
        {
            "id": int(r["id"]),
            "field": r["field"],
            "old_value": r["old_value"],
            "new_value": r["new_value"],
            "changed_at": r["changed_at"].isoformat()
            if isinstance(r["changed_at"], datetime)
            else str(r["changed_at"]),
            "source": r["source"],
            "rollback_of": int(r["rollback_of"]) if r["rollback_of"] else None,
        }
        for r in rows
    ]


async def fetch_change(pool, user_id: int, change_id: int) -> dict[str, Any] | None:
    """Fetch a single change row, scoped to the user (no cross-user leaks)."""
    r = await pool.fetchrow(
        "SELECT id, field, old_value, new_value, changed_at, source "
        "FROM config_change_log "
        "WHERE id = $1 AND user_id = $2",
        int(change_id), user_id,
    )
    if r is None:
        return None
    return {
        "id": int(r["id"]),
        "field": r["field"],
        "old_value": r["old_value"],
        "new_value": r["new_value"],
        "changed_at": r["changed_at"].isoformat()
        if isinstance(r["changed_at"], datetime)
        else str(r["changed_at"]),
        "source": r["source"],
    }
