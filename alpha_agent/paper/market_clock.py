"""Timezone-aware XNYS clock for paper runs, including shortened sessions."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from alpha_agent.market_session import _xnys_calendar

NEW_YORK = ZoneInfo("America/New_York")


def as_utc(value: datetime | str) -> datetime:
    """Parse an aware instant. Naive values are errors, never guessed UTC."""
    instant = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    if not isinstance(instant, datetime) or instant.utcoffset() is None:
        raise ValueError("timezone-aware datetime required")
    return instant.astimezone(UTC)


def market_session(now: datetime | str | None = None) -> dict:
    """Describe the NY local day's session, or the next session on a holiday.

    After close, ``session_date`` still describes today's session. During a
    weekend/holiday it describes the next trading session. ``next_open_at``
    always denotes an opening strictly after now, including while trading.
    All returned instants are ISO UTC; the date is the exchange's local date.
    """
    instant = as_utc(now) if now is not None else datetime.now(UTC)
    calendar = _xnys_calendar()
    local_day = instant.astimezone(NEW_YORK).date()
    session = calendar.date_to_session(local_day, direction="next")
    opening = as_utc(calendar.session_open(session).to_pydatetime())
    closing = as_utc(calendar.session_close(session).to_pydatetime())
    next_session = session if instant < opening else calendar.next_session(session)
    next_open = as_utc(calendar.session_open(next_session).to_pydatetime())
    return {
        "session_date": session.date().isoformat(),
        "is_open": opening <= instant < closing,
        "open_at": opening.isoformat(),
        "close_at": closing.isoformat(),
        "next_open_at": next_open.isoformat(),
    }


def target_slot_times(
    now: datetime | str | None = None,
    open_offset: int = 30,
    close_offset: int = 30,
) -> dict:
    """Return this clock session's two slots, in minutes from actual open/close.

    This returns passed slots too: the scheduler, not this helper, decides
    lateness and skip policy. On nontrading dates it returns next session slots.
    """
    session = market_session(now)
    opening, closing = as_utc(session["open_at"]), as_utc(session["close_at"])
    duration = (closing - opening).total_seconds() / 60
    for offset in (open_offset, close_offset):
        if isinstance(offset, bool) or not isinstance(offset, int) or not 0 <= offset < duration:
            raise ValueError("slot offsets must be nonnegative whole minutes within session")
    return {
        "session_date": session["session_date"],
        "open_after": (opening + timedelta(minutes=open_offset)).isoformat(),
        "close_before": (closing - timedelta(minutes=close_offset)).isoformat(),
    }
