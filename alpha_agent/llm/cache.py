"""Per-user LLM response cache (B3, 2026-05-19).

BYOK trust model: every cache row is user-scoped via the composite
(hash, user_id) primary key. A hit on user A's row never returns to
user B even when inputs hash identically — the user paid the LLM
charge that produced the row, so the row is theirs.

Cache key derivation is deterministic over:
  - model string (e.g. "kimi-for-coding", "openai/gpt-4o")
  - the exact message sequence (role + content, order-sensitive)
  - an optional variant string the caller folds in (commonly the
    ticker + as_of_date, so a brief regenerated tomorrow rolls to a
    fresh hash without polluting today's hit-rate).

TTL defaults:
  - CACHE_TTL_DEFAULT = 24h. Suitable for Rich Brief / news enrich.
  - CACHE_TTL_EOD = 7d. Suitable for slow, EOD-stable reports.

Streaming consumers (brief_streamer) cache the full accumulated text
after a successful stream, then on a hit replay it through the
section-splitter as a single chunk. Cache hit latency is sub-100ms so
the cosmetic loss of token-by-token streaming is acceptable.
"""
from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from alpha_agent.llm.base import Message

logger = logging.getLogger(__name__)

CACHE_TTL_DEFAULT: timedelta = timedelta(hours=24)
CACHE_TTL_EOD: timedelta = timedelta(days=7)


def cache_key(
    model: str,
    messages: Sequence[Message],
    variant: str = "",
) -> str:
    """Stable sha256 hash of the cacheable inputs.

    The hash is intentionally agnostic to per-request knobs that do not
    change semantic output (temperature, max_tokens) — callers that DO
    care about those should fold them into `variant`. Order-sensitive
    by design (system before user matters).
    """
    payload: dict[str, Any] = {
        "model": model,
        "messages": [(m.role, m.content) for m in messages],
        "variant": variant,
    }
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def cached_response(
    pool, user_id: int, key: str,
) -> str | None:
    """Return cached response text or None on miss / expired."""
    row = await pool.fetchrow(
        "SELECT response FROM llm_cache "
        "WHERE hash = $1 AND user_id = $2 AND expires_at > now()",
        key, user_id,
    )
    return row["response"] if row is not None else None


async def store_response(
    pool,
    user_id: int,
    key: str,
    model: str,
    response_text: str,
    ttl: timedelta = CACHE_TTL_DEFAULT,
) -> None:
    """Upsert a response into the cache. Caller is responsible for picking
    the TTL window (CACHE_TTL_DEFAULT for intraday, CACHE_TTL_EOD for
    daily/weekly reports). On hash collision (same user re-running the
    same prompt) the prior row is overwritten and TTL reset."""
    expires = datetime.now(UTC) + ttl
    try:
        await pool.execute(
            "INSERT INTO llm_cache "
            "  (hash, user_id, model, response, expires_at) "
            "VALUES ($1, $2, $3, $4, $5) "
            "ON CONFLICT (hash, user_id) DO UPDATE SET "
            "  response = EXCLUDED.response, "
            "  expires_at = EXCLUDED.expires_at, "
            "  created_at = now()",
            key, user_id, model, response_text, expires,
        )
    except Exception as exc:
        # Cache write failures are non-fatal — the caller already has a
        # fresh response in hand. Log and move on rather than failing the
        # whole request. Recurring failures show up in /admin/cache_stats.
        logger.warning(
            "llm_cache write failed for user=%s hash=%s: %s: %s",
            user_id, key[:12], type(exc).__name__, exc,
        )


async def cache_stats(pool) -> list[dict[str, Any]]:
    """Per-user cache size + freshness. Drives /admin/cache_stats."""
    rows = await pool.fetch(
        "SELECT user_id, "
        "  count(*) AS total_rows, "
        "  count(*) FILTER (WHERE expires_at > now()) AS live_rows, "
        "  max(created_at) AS last_write, "
        "  sum(length(response)) AS bytes_stored "
        "FROM llm_cache GROUP BY user_id ORDER BY user_id"
    )
    return [
        {
            "user_id": r["user_id"],
            "total_rows": int(r["total_rows"]),
            "live_rows": int(r["live_rows"]),
            "last_write": r["last_write"].isoformat() if r["last_write"] else None,
            "bytes_stored": int(r["bytes_stored"] or 0),
        }
        for r in rows
    ]


async def purge_expired(pool) -> int:
    """Sweep expired rows. Returns rows deleted. Safe to call from any
    cron tick or admin endpoint; idempotent."""
    result = await pool.execute(
        "DELETE FROM llm_cache WHERE expires_at <= now()"
    )
    # asyncpg returns "DELETE <n>" — parse the count out.
    try:
        return int(result.split()[-1])
    except (ValueError, IndexError):
        return 0
