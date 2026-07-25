"""Retention pruning for the unbounded ingestion tables.

The Neon free tier gives 0.5 GB of storage and this project has filled it three
times (2026-06-26, 2026-07-08 DiskFullError; 2026-07-25 it was the transfer
quota that blew first, with storage already at 460/500 MB). `minute_bars` has
had a prune since the first incident; `daily_signals_fast` and `news_items`
never did — they grow until the DB is full.

DELETE never extends the data file, so every prune here is safe to run even at
the size limit: it is the operation that frees space. Reclaiming the space back
to the filesystem still needs a VACUUM FULL, which needs temp room — see the
Aug-1 runbook in docs/runbooks/.
"""
from __future__ import annotations

from typing import Optional

# news sentiment is a short-horizon signal; a month is generous for any
# backfill or freshness check that reads this table.
NEWS_ITEMS_RETENTION_DAYS = 30

# Raw per-day signal rows. The DURABLE consistency history lives in
# consistency_outcomes (V035), which stores the verdict rather than the signal
# precisely so these can be pruned — but only up to what has been materialized.
DAILY_SIGNALS_RETENTION_DAYS = 30


async def prune_news_items(pool, days: int = NEWS_ITEMS_RETENTION_DAYS) -> str:
    """Delete news_items older than `days` (by published_at)."""
    return await pool.execute(
        "DELETE FROM news_items WHERE published_at < now() - make_interval(days => $1)",
        days,
    )


async def prune_daily_signals(
    pool,
    days: int = DAILY_SIGNALS_RETENTION_DAYS,
    *,
    table: str = "daily_signals_fast",
) -> str:
    """Delete signal rows older than `days`, but NEVER past the materializer.

    consistency_outcomes is what makes this safe, so the interlock is: only drop
    dates the materializer has already turned into durable verdicts. If it has
    never run (max(date) IS NULL) or has fallen behind, we prune less — or
    nothing — rather than silently destroying consistency history we cannot
    rebuild. Fail-safe, not fail-fast: a table that stays too big is recoverable,
    a deleted history is not.

    NOTE: `LEAST(d, NULL)` returns d in Postgres (NULLs are ignored), so the
    cutoff is resolved in Python instead — the obvious SQL one-liner here is a
    silent data-loss bug.
    """
    if table not in ("daily_signals_fast", "daily_signals_slow"):
        raise ValueError(f"unexpected table {table!r}")  # never interpolate free text

    materialized_through: Optional[object] = await pool.fetchval(
        "SELECT max(date) FROM consistency_outcomes"
    )
    if materialized_through is None:
        return "SKIP 0 (consistency_outcomes empty — refusing to prune)"

    status = await pool.execute(
        f"DELETE FROM {table} "  # noqa: S608 — table is whitelisted above
        "WHERE date < (current_date - make_interval(days => $1))::date "
        "  AND date <= $2",
        days,
        materialized_through,
    )
    return f"{status} (materialized through {materialized_through})"
