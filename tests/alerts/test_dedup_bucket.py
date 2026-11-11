from datetime import UTC, datetime, timedelta, timezone

import pytest

from alpha_agent.orchestrator.alert_detector import alert_dedup_bucket


@pytest.mark.parametrize("alert_type", ["news_velocity", "iv_spike"])
def test_state_alerts_dedupe_across_half_hours_until_next_utc_day(alert_type):
    morning = datetime(2026, 11, 11, 0, 1, tzinfo=UTC)
    evening = datetime(2026, 11, 11, 23, 59, tzinfo=UTC)
    tomorrow = datetime(2026, 11, 12, 0, 0, tzinfo=UTC)
    bucket = alert_dedup_bucket(alert_type, morning)
    assert bucket == int(morning.timestamp()) // 86400
    assert alert_dedup_bucket(alert_type, evening) == bucket
    assert alert_dedup_bucket(alert_type, tomorrow) == bucket + 1
    # Local calendar day is irrelevant to write-time UTC deduplication.
    assert alert_dedup_bucket(
        alert_type, tomorrow.astimezone(timezone(timedelta(hours=-5))),
    ) == bucket + 1


@pytest.mark.parametrize("alert_type", ["rating_change", "gap_3sigma", "score_spike"])
def test_event_alerts_keep_half_hour_buckets(alert_type):
    start = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
    bucket = alert_dedup_bucket(alert_type, start)
    assert bucket == int(start.timestamp()) // 1800
    assert alert_dedup_bucket(alert_type, start + timedelta(minutes=29)) == bucket
    assert alert_dedup_bucket(alert_type, start + timedelta(minutes=30)) == bucket + 1


def test_naive_alert_time_is_utc():
    naive = datetime(2026, 11, 11, 12)
    assert alert_dedup_bucket("news_velocity", naive) == alert_dedup_bucket(
        "news_velocity", naive.replace(tzinfo=UTC),
    )
