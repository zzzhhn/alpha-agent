"""Sidebar status rules: exchange-session freshness and deliberate pauses."""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from alpha_agent.api.nav_status import classify_evolution, classify_picks
from alpha_agent.market_session import latest_completed_xnys_session


def _picks(now, latest, *, behind, last_publish=None, passed=True,
           expected=date(2026, 11, 10), next_session=date(2026, 11, 11)):
    return classify_picks(
        latest_market_date=latest, latest_health_passed=passed,
        expected_session=expected, sessions_behind=behind,
        next_session=next_session, last_publish=last_publish, now=now,
    )


def test_friday_snapshot_stays_current_through_weekend():
    saturday = datetime(2026, 11, 14, 18, tzinfo=UTC)
    sunday_night = datetime(2026, 11, 16, 3, tzinfo=UTC)
    for now in (saturday, sunday_night):
        expected = latest_completed_xnys_session(now)
        assert expected == date(2026, 11, 13)
        result = _picks(now, date(2026, 11, 13), behind=0, expected=expected,
                        next_session=date(2026, 11, 16))
        assert result["state"] == "current"


def test_new_session_inside_publication_window_is_awaiting_not_failed():
    # 2026-11-10 closed; the natural 23:00 UTC run has not finished yet.
    now = datetime(2026, 11, 10, 23, 40, tzinfo=UTC)
    result = _picks(now, date(2026, 11, 9), behind=1)
    assert result["state"] == "awaiting_publish"
    assert result["next_publish_at"] == "2026-11-10T23:00:00+00:00"


def test_late_publication_after_allowance_is_delayed_not_unknown():
    # Observed 2026-11-11: GitHub fired 3.5h late and prices were not ready.
    now = datetime(2026, 11, 11, 8, tzinfo=UTC)
    result = _picks(now, date(2026, 11, 9), behind=1)
    assert result["state"] == "delayed"
    assert result["reason"] == "not_published"
    assert result["next_publish_at"] == "2026-11-11T23:00:00+00:00"


def test_failed_attempt_for_the_session_is_reported_as_failed():
    now = datetime(2026, 11, 11, 1, tzinfo=UTC)
    attempt = {"started_at": datetime(2026, 11, 10, 23, 35, tzinfo=UTC), "ok": False,
               "reason": "run_health_gate_failed"}
    result = _picks(now, date(2026, 11, 9), behind=1, last_publish=attempt)
    assert result["state"] == "failed"
    assert result["reason"] == "run_health_gate_failed"


def test_old_failure_does_not_blame_a_newer_session():
    now = datetime(2026, 11, 10, 23, 30, tzinfo=UTC)
    old = {"started_at": datetime(2026, 11, 5, 23, 30, tzinfo=UTC), "ok": False,
           "reason": "publish_exception"}
    assert _picks(now, date(2026, 11, 9), behind=1, last_publish=old)["state"] == "awaiting_publish"


def test_two_missed_sessions_are_stale():
    now = datetime(2026, 11, 12, 6, tzinfo=UTC)
    result = _picks(now, date(2026, 11, 9), behind=2, expected=date(2026, 11, 11),
                    next_session=date(2026, 11, 12))
    assert result["state"] == "stale"
    assert result["sessions_behind"] == 2


def test_no_snapshot_is_unknown_never_green():
    now = datetime(2026, 11, 11, 8, tzinfo=UTC)
    assert _picks(now, None, behind=0)["state"] == "unknown"


def test_dst_shift_keeps_post_close_schedule():
    # Before and after 2026-11-01 the 23:00 UTC run remains after the close.
    for session in (date(2026, 10, 30), date(2026, 11, 2)):
        now = datetime.combine(session, datetime.min.time(), UTC) + timedelta(hours=23, minutes=30)
        result = _picks(now, session - timedelta(days=3), behind=1, expected=session,
                        next_session=session + timedelta(days=1))
        assert result["state"] == "awaiting_publish"


NOW = datetime(2026, 11, 11, 8, tzinfo=UTC)


@pytest.mark.parametrize(
    ("workflow", "last_run", "expected"),
    [
        ("disabled_manually", None, "disabled"),
        ("disabled_manually", {"started_at": NOW - timedelta(days=9),
                               "finished_at": NOW - timedelta(days=9), "ok": False},
         "paused_after_failure"),
        ("not_found", None, "not_configured"),
        ("active", {"started_at": NOW - timedelta(hours=3),
                    "finished_at": NOW - timedelta(hours=3), "ok": True}, "idle"),
        ("active", {"started_at": NOW - timedelta(hours=26),
                    "finished_at": NOW - timedelta(hours=26), "ok": True}, "awaiting_schedule"),
        ("active", {"started_at": NOW - timedelta(hours=40),
                    "finished_at": NOW - timedelta(hours=40), "ok": True}, "schedule_missed"),
        ("active", {"started_at": NOW - timedelta(hours=2),
                    "finished_at": NOW - timedelta(hours=2), "ok": False}, "failed"),
        ("active", None, "awaiting_schedule"),
        (None, {"started_at": NOW - timedelta(hours=2),
                "finished_at": NOW - timedelta(hours=2), "ok": True}, "unknown"),
        (None, {"started_at": NOW - timedelta(minutes=3), "finished_at": None, "ok": None},
         "running"),
    ],
)
def test_evolution_states(workflow, last_run, expected):
    result = classify_evolution(workflow_state=workflow, last_run=last_run,
                                pending_reviews=0, now=NOW)
    assert result["state"] == expected


def test_deliberate_disable_is_not_reported_as_failure():
    result = classify_evolution(workflow_state="disabled_manually", last_run=None,
                                pending_reviews=2, now=NOW)
    assert result["state"] == "disabled"
    assert result["pending_reviews"] == 2
