from datetime import UTC, date, datetime

from alpha_agent.market_session import (
    is_xnys_session,
    latest_completed_xnys_session,
)


def test_before_market_close_uses_previous_session():
    assert latest_completed_xnys_session(
        datetime(2026, 8, 3, 12, tzinfo=UTC)
    ) == date(2026, 7, 31)


def test_after_market_close_uses_current_session():
    assert latest_completed_xnys_session(
        datetime(2026, 8, 3, 22, tzinfo=UTC)
    ) == date(2026, 8, 3)


def test_weekend_rolls_back_and_is_not_a_session():
    assert latest_completed_xnys_session(
        datetime(2026, 8, 1, 12, tzinfo=UTC)
    ) == date(2026, 7, 31)
    assert is_xnys_session(date(2026, 8, 1)) is False
