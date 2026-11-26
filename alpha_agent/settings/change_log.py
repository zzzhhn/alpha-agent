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

import json
from datetime import datetime
from typing import Any


ROLLBACK_SAFE_FIELDS = {"byok.model": "model", "byok.base_url": "base_url"}


async def record_change(
    pool,
    user_id: int,
    field: str,
    old_value: Any | None,
    new_value: Any | None,
    source: str = "manual",
    rollback_of: int | None = None,
    *,
    evidence: dict[str, Any] | None = None,
) -> int:
    """Append a change_log row. Returns the new row id.

    Values are str-coerced; pass JSON-stringified payloads for complex
    types if the caller needs to round-trip them. None becomes SQL NULL.
    Callers can share their settings transaction with the journal write.
    """
    def _to_text(v: Any | None) -> str | None:
        if v is None:
            return None
        return str(v)

    row = await pool.fetchrow(
        "INSERT INTO config_change_log "
        "  (user_id, field, old_value, new_value, source, rollback_of, evidence, changed_at) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, clock_timestamp()) "
        "RETURNING id",
        user_id, field, _to_text(old_value), _to_text(new_value),
        source, rollback_of, json.dumps(evidence) if evidence is not None else None,
    )
    return int(row["id"])


_CHANGE_COLUMNS = """
    c.id, c.field, c.old_value, c.new_value, c.changed_at, c.source,
    c.rollback_of, c.evidence, EXISTS (
        SELECT 1 FROM config_change_log undone
        WHERE undone.user_id = c.user_id AND undone.rollback_of = c.id
    ) AS already_rolled_back
"""


def _change_dict(row) -> dict[str, Any]:
    change = dict(row)
    if isinstance(change["changed_at"], datetime):
        change["changed_at"] = change["changed_at"].isoformat()
    return change


async def fetch_history(pool, user_id: int, limit: int = 50) -> list[dict[str, Any]]:
    """Recent changes with rollback evidence for the settings route."""
    rows = await pool.fetch(
        f"SELECT {_CHANGE_COLUMNS} FROM config_change_log c "
        "WHERE c.user_id = $1 ORDER BY c.changed_at DESC, c.id DESC LIMIT $2",
        user_id, limit,
    )
    return [_change_dict(row) for row in rows]


async def fetch_change(pool, user_id: int, change_id: int) -> dict[str, Any] | None:
    """Fetch a single change row, scoped to the user."""
    row = await pool.fetchrow(
        f"SELECT {_CHANGE_COLUMNS} FROM config_change_log c WHERE c.id = $1 AND c.user_id = $2",
        change_id, user_id,
    )
    return _change_dict(row) if row is not None else None
