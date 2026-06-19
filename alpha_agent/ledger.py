"""Daily-close product ledger writer (orchestration layer).

Reads the canonical picks view via build_lean_view (the SAME assembly the
/api/picks/lean endpoint serves) and records it as one immutable research_run
+ its rating_snapshot rows. Idempotent per market date: the first complete run
of the day is recorded; a re-fire is a no-op (append-only, never an overwrite).

The low-level INSERTs + the append-only invariant live in
storage/product_ledger.py; this module is the thin "assemble what the user saw
+ stamp provenance" step that a cron calls after a full run completes.
"""
from __future__ import annotations

import os
import subprocess
from datetime import UTC, date, datetime

from alpha_agent.api.routes.picks import LeanCard, build_lean_view
from alpha_agent.storage.product_ledger import (
    LedgerConflict,
    RatingSnapshot,
    RunMeta,
    record_research_run,
)

# The default view already serves yfinance close-adjusted prices; the
# dead-feed guard inside build_lean_view drops untradeable names, so every
# card it returns is a fresh, eligible pick.
_PRICE_SOURCE = "yfinance"
_ADJUSTMENT_MODE = "adjusted"


def code_version() -> str | None:
    """Best-effort git sha. Vercel injects VERCEL_GIT_COMMIT_SHA in prod;
    locally fall back to `git rev-parse`. None if neither is available
    (never raises — provenance is best-effort, not a hard dependency)."""
    sha = os.environ.get("VERCEL_GIT_COMMIT_SHA")
    if sha:
        return sha[:12]
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=2, check=True,
        )
        return out.stdout.strip() or None
    except Exception:
        return None


def _snapshot_from_card(card: LeanCard, rank: int) -> RatingSnapshot:
    """Map an emitted LeanCard to its immutable ledger row. The full card is
    stored verbatim in user_visible_payload so the record is exactly what the
    user saw; the scalar columns (rank/tier/composite_z) are denormalized for
    cheap querying by the L2 / forward-IC consumers."""
    return RatingSnapshot(
        ticker=card.ticker,
        composite_z=card.composite_score,
        rank=rank,
        tier=card.rating,
        in_universe=True,
        eligible=True,
        eligibility_reason=None,
        user_visible_payload=card.model_dump(),
        price_source=_PRICE_SOURCE,
        adjustment_mode=_ADJUSTMENT_MODE,
        feed_status="fresh",
    )


async def record_daily_close(
    pool,
    *,
    scheduled_for_date: date | None = None,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
    weight_policy_id: str | None = None,
    registry_hash: str | None = None,
    tier_threshold_version: str | None = None,
    status: str = "complete",
    allow_correction: bool = False,
    on_conflict: str = "skip",
) -> int | None:
    """Snapshot the canonical default picks view into the ledger.

    Returns the new run id, or None when on_conflict='skip' and a complete run
    already exists for the date (the first run of the day wins; re-fires are a
    no-op). Set allow_correction=True to deliberately record a superseding
    correction (a new run id; the earlier run is never mutated).

    The view captured is the user-facing default: full universe, long side,
    short mode — the same one /api/picks/lean serves with no params.
    """
    now = datetime.now(UTC)
    for_date = scheduled_for_date or now.date()
    started = started_at or now

    cards, as_of, _stale = await build_lean_view(
        pool, limit=600, search=None, mode="short", side="long"
    )
    snapshots = [_snapshot_from_card(c, i) for i, c in enumerate(cards, start=1)]

    if weight_policy_id is None:
        try:
            from alpha_agent.fusion.policy import get_active_policy
            weight_policy_id = get_active_policy().policy_id
        except Exception:
            weight_policy_id = None

    meta = RunMeta(
        scheduled_for_date=for_date,
        status=status,
        started_at=started,
        finished_at=finished_at or datetime.now(UTC),
        run_type="daily_close",
        data_asof=as_of,
        input_data_cutoff=as_of,
        code_version=code_version(),
        registry_hash=registry_hash,
        weight_policy_id=weight_policy_id,
        tier_threshold_version=tier_threshold_version,
    )

    try:
        return await record_research_run(
            pool, meta, snapshots, allow_correction=allow_correction
        )
    except LedgerConflict:
        if on_conflict == "skip":
            return None
        raise
