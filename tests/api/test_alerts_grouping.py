from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from alpha_agent.api.routes import alerts


def _row(alert_id, created_at, *, ticker="AAPL", alert_type="news_velocity", payload=None):
    return {
        "id": alert_id, "ticker": ticker, "type": alert_type,
        "payload": payload or {"n_24h": 12}, "dedup_bucket": alert_id,
        "created_at": datetime.fromisoformat(created_at),
    }


def _state(alert_id, status):
    return {
        "alert_id": alert_id, "status": status,
        "snooze_until": datetime(2026, 11, 12, tzinfo=UTC) if status == "snoozed" else None,
        "resolved_at": datetime(2026, 11, 11, tzinfo=UTC) if status == "resolved" else None,
        "note": None, "updated_at": datetime(2026, 11, 11, tzinfo=UTC),
    }


def _pool(monkeypatch, rows, states=()):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 11, 18, tzinfo=UTC)

    monkeypatch.setattr(alerts, "datetime", Clock)
    monkeypatch.setattr(alerts, "_decision_context", AsyncMock(return_value=({"AAPL"}, set(), {})))
    pool = MagicMock()
    pool.fetch = AsyncMock(side_effect=[rows, list(states)] if rows else [rows])
    return pool


@pytest.mark.parametrize(("older", "newer", "separate"), [
    ("2026-11-11T23:30:00+00:00", "2026-11-12T00:30:00+00:00", False),
    ("2026-11-11T04:59:00+00:00", "2026-11-11T05:01:00+00:00", True),
    ("2026-07-11T03:59:00+00:00", "2026-07-11T04:01:00+00:00", True),
    # DST fallback repeats an hour within the same NY day.
    ("2026-11-01T05:30:00+00:00", "2026-11-01T06:30:00+00:00", False),
])
async def test_alert_group_uses_ny_date_not_utc_date(monkeypatch, older, newer, separate):
    rows = [_row(1, older), _row(2, newer)]  # intentionally not newest first
    inbox = await alerts._build_inbox(_pool(monkeypatch, rows), 7, 50)
    assert len(inbox.alerts) == (2 if separate else 1)
    if not separate:
        item = inbox.alerts[0]
        assert item.id == 2
        assert item.occurrences == 2
        assert item.first_seen_at == older
        assert item.last_seen_at == item.created_at == newer
        assert item.member_ids == [2, 1]
    else:
        assert all(item.occurrences == 1 and item.member_ids == [item.id] for item in inbox.alerts)


@pytest.mark.parametrize(("older_state", "newer_state", "expected"), [
    ("resolved", "resolved", "resolved"),
    ("resolved", "snoozed", "snoozed"),
    ("snoozed", "resolved", "resolved"),
    ("open", "resolved", "open"),
    ("open", "snoozed", "open"),
    ("resolved", "open", "open"),
])
async def test_alert_group_open_member_or_representative_state(
    monkeypatch, older_state, newer_state, expected,
):
    rows = [_row(2, "2026-11-11T17:55:00+00:00"), _row(1, "2026-11-11T17:30:00+00:00")]
    states = [_state(1, older_state), _state(2, newer_state)]
    inbox = await alerts._build_inbox(_pool(monkeypatch, rows, states), 7, 50)
    assert len(inbox.alerts) == 1
    assert inbox.alerts[0].state.status == expected
    assert inbox.counts.resolved == (expected == "resolved")
    assert inbox.counts.watch == (expected != "resolved")
    assert inbox.counts.needs_action == 0  # info + low stays in watch even in a position


async def test_alert_groups_keep_newest_payload_max_score_and_group_counts(monkeypatch):
    rows = [
        _row(1, "2026-11-11T17:30:00+00:00", payload={"n_24h": 30}),
        _row(2, "2026-11-11T17:55:00+00:00"),
        _row(3, "2026-11-11T17:40:00+00:00", alert_type="score_spike"),
        _row(4, "2026-11-11T17:50:00+00:00", alert_type="score_spike"),
        _row(5, "2026-11-09T17:40:00+00:00", ticker="XYZ"),
        _row(6, "2026-11-09T17:50:00+00:00", ticker="XYZ"),
        _row(7, "2026-11-11T17:40:00+00:00", ticker="MSFT"),
        _row(8, "2026-11-11T17:50:00+00:00", ticker="MSFT"),
    ]
    states = [_state(7, "resolved"), _state(8, "resolved")]
    inbox = await alerts._build_inbox(_pool(monkeypatch, rows, states), 7, 50)
    assert len(inbox.alerts) == 4
    item = inbox.alerts[0]
    assert item.id == 2 and item.payload == {"n_24h": 12}
    assert item.severity == "info"  # all representative fields except score/state are newest
    assert item.triage_score == 90
    assert inbox.counts.model_dump() == {"needs_action": 1, "watch": 1, "record": 1, "resolved": 1}
    assert [(item.triage_score, item.created_at) for item in inbox.alerts] == sorted(
        [(item.triage_score, item.created_at) for item in inbox.alerts], reverse=True,
    )
