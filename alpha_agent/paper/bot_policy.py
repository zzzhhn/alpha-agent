"""Small deterministic readiness/evidence policies. No provider calls or writes."""
from datetime import UTC, date, datetime

from alpha_agent.market_session import _xnys_calendar
from alpha_agent.paper.market_clock import NEW_YORK, as_utc, market_session

MODEL_TIMEOUT_SECONDS = 250
EXECUTION_RESERVE_SECONDS = 180


def research_age(source, now=None):
    """Count exchange sessions, not natural days; future/unknown evidence stays unknown."""
    if not source:
        return None
    instant = now or datetime.now(UTC)
    value = source.get('scheduled_for_date') or source.get('market_date') or source.get('data_asof')
    if value is None:
        return None
    try:
        cutoff = source.get('data_asof')
        if cutoff and as_utc(cutoff) > instant:
            return None
        if isinstance(value, datetime):
            day = as_utc(value).astimezone(NEW_YORK).date()
        elif isinstance(value, date):
            day = value
        else:
            day = date.fromisoformat(str(value)[:10])
        target = date.fromisoformat(market_session(instant)['session_date'])
        if day > target:
            return None
        calendar = _xnys_calendar()
        start = calendar.date_to_session(day, direction='previous')
        end = calendar.date_to_session(target, direction='previous')
        return len(calendar.sessions_in_range(start, end)) - 1
    except (TypeError, ValueError, OverflowError):
        return None


def model_budget(run, now=None):
    """Do not start a full patient model request if it would consume execution time."""
    remaining = (as_utc(run['expires_at']) - (now or datetime.now(UTC))).total_seconds()
    return {'remaining_seconds': max(0, round(remaining)),
            'model_timeout_seconds': MODEL_TIMEOUT_SECONDS,
            'execution_reserve_seconds': EXECUTION_RESERVE_SECONDS,
            'can_call_model': remaining >= MODEL_TIMEOUT_SECONDS + EXECUTION_RESERVE_SECONDS}


def readiness(config, account, today_runs, active, source, capacity, now=None):
    instant = now or datetime.now(UTC)
    market = market_session(instant)
    blocked = []
    if account['status'] != 'active':
        blocked.append('account_inactive')
    if not config['credential_configured']:
        blocked.append('credential_missing')
    if not capacity['allow_writes']:
        blocked.append('storage_headroom_low')
    if active:
        blocked.append('run_active')
    if today_runs >= config['max_daily_runs']:
        blocked.append('daily_limit')
    if not market['is_open']:
        blocked.append('market_closed')
    elif (as_utc(market['close_at']) - instant).total_seconds() < MODEL_TIMEOUT_SECONDS + EXECUTION_RESERVE_SECONDS + 60:
        blocked.append('near_close')
    age = research_age(source, instant)
    warnings = []
    if source is None or age is None:
        warnings.append('research_unavailable')
    elif age > config.get('max_research_age_sessions', 3):
        warnings.append('research_stale')
    return {
        'evaluated_at': instant.isoformat(), 'can_wake': not blocked,
        'blocked_reasons': blocked, 'warnings': warnings,
        'schedule_reason': 'schedule_disabled' if not config['schedule_enabled'] else
                           'no_slots_enabled' if not (config['open_enabled'] or config['close_enabled']) else 'scheduled',
        'today_runs': today_runs, 'research_as_of': str(source['data_asof']) if source and source.get('data_asof') else None,
        'research_age_sessions': age,
    }
