"""Pure classification rules for the sidebar navigation status contract.

The sidebar shows a hint only when a stable, evidence-backed state can point
the user to a next step. These functions classify already-fetched facts. They
never perform I/O, retries or model calls, so they stay cheap and testable.
"""
from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Literal

PicksState = Literal["current", "awaiting_publish", "delayed", "stale", "failed", "unknown"]
EvolutionState = Literal[
    "running",
    "idle",
    "awaiting_schedule",
    "schedule_missed",
    "failed",
    "paused_after_failure",
    "disabled",
    "not_configured",
    "unknown",
]

# cron-shards.yml dispatches the complete research refresh at 23:00 UTC on
# weekdays, after the XNYS close in both DST regimes. The run then needs about
# 40 minutes. GitHub schedules are best-effort, so the status only reports a
# delay after this allowance rather than at the nominal minute.
PUBLISH_SCHEDULE_UTC = time(23, 0, tzinfo=UTC)
PUBLISH_ALLOWANCE = timedelta(hours=3)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def publish_start(session: date) -> datetime:
    """Nominal start of the natural snapshot publication for ``session``."""
    return datetime.combine(session, PUBLISH_SCHEDULE_UTC)


def classify_picks(
    *,
    latest_market_date: date | None,
    latest_health_passed: bool | None,
    expected_session: date,
    sessions_behind: int,
    next_session: date,
    last_publish: dict[str, Any] | None,
    now: datetime,
) -> dict[str, Any]:
    """Exchange-session aware freshness of the published recommendation.

    ``expected_session`` is the latest completed XNYS session, so weekends and
    holidays never age a healthy Friday snapshot. ``sessions_behind`` counts the
    completed sessions newer than the latest snapshot.
    """
    now = _aware(now) or datetime.now(UTC)
    due_at = publish_start(expected_session)
    base: dict[str, Any] = {
        "market_date": latest_market_date.isoformat() if latest_market_date else None,
        "expected_market_date": expected_session.isoformat(),
        "sessions_behind": sessions_behind,
    }
    if latest_market_date is None:
        return {**base, "state": "unknown", "reason": "no_published_snapshot",
                "next_publish_at": None}
    if sessions_behind <= 0 and latest_health_passed is not False:
        return {**base, "state": "current", "reason": None,
                "next_publish_at": publish_start(next_session).isoformat()}

    attempt = last_publish or {}
    attempt_at = _aware(attempt.get("started_at"))
    attempt_failed = attempt.get("ok") is False
    # A failed publish only explains this session when it started after the
    # session's own natural window opened (late GitHub starts still count).
    if attempt_failed and attempt_at is not None and attempt_at >= due_at - timedelta(hours=2):
        return {**base, "state": "failed",
                "reason": attempt.get("reason") or "publish_failed",
                "next_publish_at": publish_start(next_session).isoformat()}

    pending = now < due_at + PUBLISH_ALLOWANCE
    if sessions_behind >= 2 or (sessions_behind == 1 and latest_health_passed is False):
        state: PicksState = "stale"
        reason = "sessions_missed"
    elif pending:
        state, reason = "awaiting_publish", "within_publication_window"
    else:
        # The price-readiness pause runs inside GitHub Actions and writes no
        # durable row, so the exact cause is not claimed here.
        state, reason = "delayed", "not_published"
    next_at = due_at if pending else publish_start(next_session)
    return {**base, "state": state, "reason": reason, "next_publish_at": next_at.isoformat()}


def classify_evolution(
    *,
    workflow_state: str | None,
    last_run: dict[str, Any] | None,
    pending_reviews: int | None,
    now: datetime,
    cadence: timedelta = timedelta(hours=24),
    late_after: timedelta = timedelta(hours=6),
) -> dict[str, Any]:
    """Separate deliberate or automatic pauses from failures and idle time.

    ``workflow_state`` is the GitHub Actions state of the daily factor loop
    (``active``, ``disabled_manually``, ``not_found``) or None when the
    scheduler could not be read. Durable run rows alone can still establish a
    running or failed state; they cannot prove a pause.
    """
    now = _aware(now) or datetime.now(UTC)
    run = last_run or {}
    finished = _aware(run.get("finished_at"))
    started = _aware(run.get("started_at"))
    last_failed = run.get("ok") is False
    disabled = bool(workflow_state and workflow_state.startswith("disabled"))
    if started and finished is None and now - started < timedelta(minutes=15):
        state: EvolutionState = "running"
    elif disabled and last_failed:
        # The circuit breaker disables a workflow after a failed scheduled run.
        state = "paused_after_failure"
    elif disabled:
        state = "disabled"
    elif workflow_state == "not_found":
        state = "not_configured"
    elif last_failed:
        state = "failed"
    elif workflow_state is None:
        state = "unknown"
    elif not last_run:
        state = "awaiting_schedule"
    elif finished is not None and now - finished > cadence + late_after:
        state = "schedule_missed"
    elif finished is not None and now - finished > cadence:
        state = "awaiting_schedule"
    else:
        state = "idle"
    observed = finished or started
    return {
        "state": state,
        "workflow_state": workflow_state,
        "last_run_at": observed.isoformat() if observed else None,
        "last_run_ok": run.get("ok") if last_run else None,
        "pending_reviews": pending_reviews,
    }
