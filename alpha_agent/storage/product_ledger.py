"""Append-only product ledger: writer + readers.

The engine's causal memory. Records, immutably, WHAT a run was (provenance)
and WHAT the user saw (the emitted picks). Schema: migration V024.

Append-only contract (see V024 header): this module only ever INSERTs.
A correction is a NEW run id; the earlier run is never UPDATEd or DELETEd.
The "one canonical run per market date" rule is resolved at read time
(get_canonical_run = latest finished_at among complete runs). A duplicate
COMPLETE run for the same (date, run_type) is refused by default to stop an
accidental cron double-fire; pass allow_correction=True to record a
deliberate superseding correction.

This module stays pure persistence: dataclasses + asyncpg, no fusion / api /
signal imports, so it never pulls the alpha stack into a cold start.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime

import asyncpg


class LedgerConflict(Exception):
    """A complete run already exists for (scheduled_for_date, run_type) and
    allow_correction was not set. The existing run is never mutated; pass
    allow_correction=True to record a superseding correction (a new run id)."""


@dataclass(frozen=True)
class RunMeta:
    """Provenance for one engine run. Everything needed to reproduce / audit
    the snapshot set: when, on what data, with which code + policy + thresholds."""

    scheduled_for_date: date
    status: str  # 'started' | 'partial' | 'complete' | 'failed' | 'corrected'
    started_at: datetime
    finished_at: datetime | None = None
    run_type: str = "daily_close"
    data_asof: datetime | None = None
    input_data_cutoff: datetime | None = None
    code_version: str | None = None
    registry_hash: str | None = None
    weight_policy_id: str | None = None
    tier_threshold_version: str | None = None


@dataclass(frozen=True)
class RatingSnapshot:
    """One ticker's emitted state in a run: what the user saw + how it was
    eligible + the price provenance behind it."""

    ticker: str
    composite_z: float | None = None
    rank: int | None = None
    tier: str | None = None
    coverage: float | None = None
    in_universe: bool = True
    eligible: bool = True
    eligibility_reason: str | None = None
    effective_weight: dict = field(default_factory=dict)
    user_visible_payload: dict = field(default_factory=dict)
    price_source: str | None = None
    price_downloaded_at: datetime | None = None
    adjustment_mode: str | None = None
    feed_status: str | None = None


_SNAPSHOT_COLUMNS = (
    "run_id", "ticker", "in_universe", "eligible", "eligibility_reason",
    "composite_z", "rank", "tier", "coverage", "effective_weight_json",
    "user_visible_payload_json", "price_source", "price_downloaded_at",
    "adjustment_mode", "feed_status",
)

_SNAPSHOT_INSERT = f"""
    INSERT INTO rating_snapshot ({", ".join(_SNAPSHOT_COLUMNS)})
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb,
            $11::jsonb, $12, $13, $14, $15)
"""


def _snapshot_row(run_id: int, s: RatingSnapshot) -> tuple:
    return (
        run_id, s.ticker, s.in_universe, s.eligible, s.eligibility_reason,
        s.composite_z, s.rank, s.tier, s.coverage,
        json.dumps(s.effective_weight or {}),
        json.dumps(s.user_visible_payload or {}),
        s.price_source, s.price_downloaded_at, s.adjustment_mode, s.feed_status,
    )


async def record_research_run(
    pool: asyncpg.Pool,
    run_meta: RunMeta,
    snapshots: list[RatingSnapshot],
    *,
    allow_correction: bool = False,
) -> int:
    """Append one immutable run + its snapshots. Returns the new run id.

    Raises LedgerConflict if run_meta.status == 'complete', a complete run
    already exists for (scheduled_for_date, run_type), and allow_correction
    is False. The guard + both inserts run in one transaction so a concurrent
    double-fire cannot slip two completes past the check.
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            if run_meta.status == "complete" and not allow_correction:
                exists = await conn.fetchval(
                    """
                    SELECT 1 FROM research_run
                    WHERE scheduled_for_date = $1 AND run_type = $2
                      AND status = 'complete'
                    LIMIT 1
                    """,
                    run_meta.scheduled_for_date, run_meta.run_type,
                )
                if exists:
                    raise LedgerConflict(
                        f"complete run already exists for "
                        f"{run_meta.scheduled_for_date} / {run_meta.run_type}; "
                        f"pass allow_correction=True to record a correction"
                    )

            run_id = await conn.fetchval(
                """
                INSERT INTO research_run
                    (scheduled_for_date, run_type, status, started_at,
                     finished_at, data_asof, input_data_cutoff, code_version,
                     registry_hash, weight_policy_id, tier_threshold_version)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                RETURNING id
                """,
                run_meta.scheduled_for_date, run_meta.run_type, run_meta.status,
                run_meta.started_at, run_meta.finished_at, run_meta.data_asof,
                run_meta.input_data_cutoff, run_meta.code_version,
                run_meta.registry_hash, run_meta.weight_policy_id,
                run_meta.tier_threshold_version,
            )

            if snapshots:
                await conn.executemany(
                    _SNAPSHOT_INSERT,
                    [_snapshot_row(run_id, s) for s in snapshots],
                )
            return run_id


async def get_canonical_run(
    pool: asyncpg.Pool,
    scheduled_for_date: date,
    run_type: str = "daily_close",
) -> asyncpg.Record | None:
    """The canonical run for a market date: the latest COMPLETE run by
    finished_at. partial / failed / started runs are never canonical.
    Returns None when no complete run exists for the date."""
    return await pool.fetchrow(
        """
        SELECT * FROM research_run
        WHERE scheduled_for_date = $1 AND run_type = $2 AND status = 'complete'
        ORDER BY finished_at DESC NULLS LAST, id DESC
        LIMIT 1
        """,
        scheduled_for_date, run_type,
    )


async def get_run_snapshots(
    pool: asyncpg.Pool, run_id: int
) -> list[asyncpg.Record]:
    """All snapshots for a run, ranked order first (NULL ranks last)."""
    return await pool.fetch(
        """
        SELECT * FROM rating_snapshot
        WHERE run_id = $1
        ORDER BY rank ASC NULLS LAST, ticker ASC
        """,
        run_id,
    )
