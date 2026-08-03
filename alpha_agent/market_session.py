"""New York Stock Exchange session helpers.

The product uses daily close data.  A server calendar date is therefore not a
market date: before today's close the latest completed session is yesterday's
session, and weekends/holidays must roll back through the XNYS calendar.
"""
from __future__ import annotations

from datetime import UTC, date, datetime
from functools import lru_cache


@lru_cache(maxsize=1)
def _xnys_calendar():
    import exchange_calendars as xcals

    return xcals.get_calendar("XNYS")


def latest_completed_xnys_session(now: datetime | None = None) -> date:
    """Return the latest XNYS session whose official close has passed."""
    instant = now or datetime.now(UTC)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=UTC)
    instant = instant.astimezone(UTC)

    calendar = _xnys_calendar()
    session = calendar.date_to_session(instant.date(), direction="previous")
    if calendar.session_close(session).to_pydatetime() > instant:
        session = calendar.previous_session(session)
    return session.date()


def is_xnys_session(value: date) -> bool:
    """Return whether ``value`` is an actual XNYS trading session."""
    calendar = _xnys_calendar()
    try:
        return calendar.date_to_session(value, direction="none").date() == value
    except ValueError:
        return False
