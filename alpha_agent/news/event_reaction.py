"""Point-in-time observation of official event reactions, never a fill or signal."""
from __future__ import annotations

import asyncio
import json
import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Literal

from pydantic import BaseModel

from alpha_agent.market_session import _xnys_calendar
from alpha_agent.paper.intraday import SOURCE
from alpha_agent.paper.market_clock import NEW_YORK, as_utc, market_session

MINUTE = timedelta(minutes=1)
HORIZON = timedelta(minutes=30)
CAPTURE_LAG = timedelta(minutes=8)
ANCHOR_WINDOW = timedelta(minutes=12)
MAX_EVENTS = 2
MARKET = 'SPY'
QUALITY = 'raw_unadjusted'


class ReturnPair(BaseModel):
    ticker_return: float
    spy_return: float
    excess_return: float
    price_basis: Literal['raw_unadjusted']
    source: str


class OpeningGap(ReturnPair):
    prior_close_at: datetime
    open_at: datetime


class FollowThrough(ReturnPair):
    anchor_at: datetime
    end_at: datetime


class EventReaction(BaseModel):
    status: Literal['pending', 'observed', 'partial', 'unavailable']
    session_date: date
    as_of: datetime
    timing: Literal['overnight', 'intraday', 'late_discovery']
    gap: OpeningGap | None
    follow_through: FollowThrough | None
    gap_reason: str | None
    follow_reason: str | None


@dataclass(frozen=True)
class Window:
    known: datetime
    session: date
    opening: datetime
    closing: datetime
    prior_open: datetime
    prior_close: datetime
    timing: str

    @property
    def first_minute(self) -> datetime:
        return max(self.opening, self.known.replace(second=0, microsecond=0) + MINUTE)


def _session_for(instant: datetime) -> dict:
    session = market_session(instant)
    return market_session(session['next_open_at']) if instant >= as_utc(session['close_at']) else session


def reaction_window(published_at: datetime, first_seen_at: datetime) -> Window:
    published_at, first_seen_at = as_utc(published_at), as_utc(first_seen_at)
    known = max(published_at, first_seen_at)
    target = _session_for(known)
    intended = _session_for(published_at)
    opening, closing = as_utc(target['open_at']), as_utc(target['close_at'])
    day = date.fromisoformat(target['session_date'])
    calendar = _xnys_calendar()
    prior = calendar.previous_session(calendar.date_to_session(day))
    prior_open = as_utc(calendar.session_open(prior).to_pydatetime())
    prior_close = as_utc(calendar.session_close(prior).to_pydatetime())
    if target['session_date'] != intended['session_date'] or published_at < opening <= known:
        timing = 'late_discovery'
    elif prior_close <= published_at <= known < opening:
        timing = 'overnight'
    elif known - published_at > HORIZON:
        timing = 'late_discovery'
    else:
        timing = 'intraday'
    return Window(known, day, opening, closing, prior_open, prior_close, timing)


def _finite(value) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _history(ticker: str):
    import yfinance as yf

    # One bounded unadjusted minute request covers both the current and prior
    # regular session even across weekends and early closes. No daily fallback.
    return yf.Ticker(ticker).history(period='5d', interval='1m', auto_adjust=False,
                                    back_adjust=False, actions=True, prepost=False,
                                    timeout=6, raise_errors=True)


async def fetch_reaction_bars(ticker: str) -> list[dict]:
    frame = await asyncio.to_thread(_history, ticker)
    received = datetime.now(UTC)
    if frame is None or frame.empty:
        return []
    # Detect adjustments on any reported minute of the session, not only the
    # timestamps selected for the return calculation.
    known_actions = {'Dividends', 'Stock Splits'}.issubset(frame.columns)
    session_actions = set()
    unknown_sessions = set()
    bars = []
    for key, row in frame.sort_index().tail(2000).iterrows():
        start = as_utc(key.to_pydatetime())
        local_date = start.astimezone(NEW_YORK).date()
        actions = [_finite(row.get(field)) for field in ('Dividends', 'Stock Splits')]
        if any(value not in (None, 0.0) for value in actions):
            session_actions.add(local_date)
        if None in actions:
            unknown_sessions.add(local_date)
        bars.append((local_date, {'start': start, 'end': start + MINUTE, 'fetched_at': received,
                                 'open': _finite(row.get('Open')), 'close': _finite(row.get('Close')),
                                 'volume': _finite(row.get('Volume')), 'source': SOURCE,
                                 'price_basis': QUALITY}))
    return [dict(bar, corporate_actions=day in session_actions,
                 corporate_actions_known=known_actions and day not in unknown_sessions) for day, bar in bars]


def _valid_bars(rows, now: datetime, lower: datetime, upper: datetime) -> tuple[dict, str | None]:
    out, conflicts = {}, set()
    quality = None
    for item in rows:
        try:
            start, end, fetched = (as_utc(item[k]) for k in ('start', 'end', 'fetched_at'))
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
        if not lower <= start < end <= upper or end - start != MINUTE or start.second or start.microsecond:
            continue
        if not end <= fetched <= now or item.get('price_basis') != QUALITY:
            continue
        if item.get('corporate_actions') or item.get('corporate_actions_known') is not True:
            quality = 'corporate_action_or_unknown'
            continue
        prices = [_finite(item.get(key)) for key in ('open', 'close', 'volume')]
        if not all(value is not None and value > 0 for value in prices) or not item.get('source'):
            continue
        opening, closing, _ = prices
        snapshot = {'start': start.isoformat(), 'end': end.isoformat(), 'fetched_at': fetched.isoformat(),
                    'open': opening, 'close': closing, 'source': item['source']}
        if end in out and (opening, closing, item['source']) != (out[end]['open'], out[end]['close'], out[end]['source']):
            conflicts.add(end)
        elif end not in out or snapshot['fetched_at'] < out[end]['fetched_at']:
            out[end] = snapshot
    for end in conflicts:
        out.pop(end, None)
    return out, quality


def _pair(ticker_bars, spy_bars, at: datetime) -> dict | None:
    if at in ticker_bars and at in spy_bars:
        ticker, spy = ticker_bars[at], spy_bars[at]
        if ticker['source'] == spy['source']:
            return {'ticker': ticker, 'spy': spy}
    return None


def _measured(base, end, start_key: str, end_key: str) -> dict | None:
    sources = {p[k]['source'] for p in (base, end) for k in ('ticker', 'spy')}
    if len(sources) != 1:
        return None
    stock, spy = (end[k][end_key] / base[k][start_key] - 1 for k in ('ticker', 'spy'))
    if not all(map(math.isfinite, (stock, spy, stock - spy))):
        return None
    return {'ticker_return': stock, 'spy_return': spy, 'excess_return': stock - spy,
            'price_basis': QUALITY, 'source': sources.pop(), 'evidence': {'start': base, 'end': end}}


def _unpack(value):
    return json.loads(value) if isinstance(value, str) else value


def reaction_step(window: Window, now: datetime, old: dict, ticker_rows: list[dict],
                  spy_rows: list[dict], *, provider_unavailable: bool = False) -> dict:
    """Freeze opening gap and a 30-minute mark using first-received synchronized bars."""
    gap, follow, anchor = (_unpack(old.get(key)) for key in ('gap', 'follow_through', 'anchor'))
    gap_reason, follow_reason = old.get('gap_reason'), old.get('follow_reason')
    next_checks = []

    ticker, ticker_action = _valid_bars(ticker_rows, now, window.opening, window.closing)
    spy, spy_action = _valid_bars(spy_rows, now, window.opening, window.closing)
    action = ticker_action or spy_action
    issue = 'provider_unavailable' if provider_unavailable else None

    # Gap is measured only if the release AND its first observation preceded
    # this opening. An old opening price may never be proposed as a fill.
    gap_end = window.opening + MINUTE
    if window.timing != 'overnight':
        gap_reason = 'late_discovery_no_open_gap' if window.timing == 'late_discovery' else 'not_overnight'
    elif action:
        gap, gap_reason = None, action
    elif gap is not None:
        gap_reason = None
    elif now < gap_end:
        gap_reason = 'waiting_open'
        next_checks.append(gap_end)
    elif now <= gap_end + CAPTURE_LAG:
        prior_stock, prior_stock_action = _valid_bars(ticker_rows, now, window.prior_open, window.prior_close)
        prior_spy, prior_spy_action = _valid_bars(spy_rows, now, window.prior_open, window.prior_close)
        current_pair = _pair(ticker, spy, gap_end)
        prior_pair = _pair(prior_stock, prior_spy, window.prior_close)
        if prior_stock_action or prior_spy_action:
            gap_reason = 'corporate_action_or_unknown'
        elif current_pair and prior_pair and (gap := _measured(prior_pair, current_pair, 'close', 'open')):
            gap.update(prior_close_at=window.prior_close.isoformat(), open_at=window.opening.isoformat())
            gap_reason = None
        else:
            gap_reason = issue or ('missing_open_pair' if not current_pair else
                                  'missing_prior_close_pair' if not prior_pair else 'unmatched_price_basis')
            next_checks.append(min(now + MINUTE, gap_end + CAPTURE_LAG + MINUTE))
    elif gap_reason in (None, 'waiting_open'):
        gap_reason = 'open_capture_window_elapsed'

    if action:
        follow, follow_reason = None, action
    elif follow is not None:
        follow_reason = None
    elif window.first_minute + MINUTE + HORIZON > window.closing:
        follow_reason = 'insufficient_regular_session'
    else:
        first_end = window.first_minute + MINUTE
        anchor_deadline = first_end + ANCHOR_WINDOW
        if not anchor and now <= anchor_deadline:
            if now < first_end:
                follow_reason = 'waiting_anchor'
                next_checks.append(first_end)
            else:
                available = sorted(end for end in ticker.keys() & spy.keys()
                                   if first_end <= end <= min(now, window.closing - HORIZON)
                                   and now - end <= CAPTURE_LAG)
                for end in available:
                    anchor = _pair(ticker, spy, end)
                    if anchor:
                        break
                if not anchor:
                    follow_reason = issue or 'missing_anchor_pair'
                    next_checks.append(min(now + MINUTE, anchor_deadline + MINUTE))
        if anchor:
            anchor_at = as_utc(anchor['ticker']['end'])
            target = anchor_at + HORIZON
            if now < target:
                follow_reason = 'waiting_30_minute_mark'
                next_checks.append(target)
            elif now <= target + CAPTURE_LAG:
                target_pair = _pair(ticker, spy, target)
                if target_pair and (follow := _measured(anchor, target_pair, 'close', 'close')):
                    follow.update(anchor_at=anchor_at.isoformat(), end_at=target.isoformat())
                    follow_reason = None
                else:
                    follow_reason = issue or ('missing_30_minute_pair' if not target_pair else 'unmatched_price_basis')
                    next_checks.append(min(now + MINUTE, target + CAPTURE_LAG + MINUTE))
            elif follow_reason in (None, 'waiting_30_minute_mark'):
                follow_reason = 'follow_capture_window_elapsed'
        elif now > anchor_deadline and follow_reason in (None, 'waiting_anchor'):
            follow_reason = 'anchor_capture_window_elapsed'

    if next_checks:
        status = 'pending'
    elif follow and (gap or window.timing != 'overnight'):
        status = 'observed'
    elif follow or gap:
        status = 'partial'
    else:
        status = 'unavailable'
    return {'status': status, 'gap': gap, 'anchor': anchor, 'follow_through': follow,
            'gap_reason': gap_reason, 'follow_reason': follow_reason,
            'next_check_at': min(next_checks) if next_checks else None}


def _needs_market(window: Window, row: dict, now: datetime) -> bool:
    gap_end = window.opening + MINUTE
    if window.timing == 'overnight' and not row.get('gap') and gap_end <= now <= gap_end + CAPTURE_LAG:
        return True
    if row.get('follow_through'):
        return False
    first_end = window.first_minute + MINUTE
    if first_end + HORIZON > window.closing:
        return False
    anchor = _unpack(row.get('anchor'))
    if anchor:
        target = as_utc(anchor['ticker']['end']) + HORIZON
        return target <= now <= target + CAPTURE_LAG
    return first_end <= now <= first_end + ANCHOR_WINDOW


async def observe_event_reactions(pool, *, now: datetime | None = None, fetcher=None) -> dict:
    """Observe at most two exact-time official events per cycle; no effect on any book."""
    stamp = as_utc(now) if now is not None else datetime.now(UTC)
    fetcher = fetcher or fetch_reaction_bars
    rows = await pool.fetch('''SELECT e.id,e.ticker,e.published_at,e.first_seen_at,
               r.gap,r.anchor,r.follow_through,r.gap_reason,r.follow_reason,r.observed_at AS previous_observed_at
        FROM official_event_watch e LEFT JOIN official_event_reaction r ON r.event_id=e.id
       WHERE e.first_seen_at <= $1 AND e.published_at <= $1
         AND (r.event_id IS NOT NULL OR e.first_seen_at >= $1 - interval '6 days')
         AND e.status='observed' AND e.published_at_quality IN ('sec_accepted','source_timestamp')
         AND e.kind IN ('management_change','earnings','guidance','merger_acquisition','regulatory')
         AND (r.event_id IS NULL OR (r.status='pending' AND r.next_check_at <= $1))
       ORDER BY (r.event_id IS NOT NULL) DESC,coalesce(r.next_check_at,e.first_seen_at),e.id LIMIT $2''', stamp, MAX_EVENTS)
    events = [(row, reaction_window(row['published_at'], row['first_seen_at'])) for row in rows]
    symbols = set()
    for row, window in events:
        # Never ask the provider for historical outcomes after the capture
        # deadline, or before its first eligible regular minute.
        if _needs_market(window, dict(row), stamp):
            symbols.update((row['ticker'], MARKET))
    semaphore = asyncio.Semaphore(2)

    async def fetch(ticker):
        try:
            async with semaphore:
                return ticker, await asyncio.wait_for(fetcher(ticker), timeout=8)
        except Exception:  # Provider exceptions become explicit missing evidence.
            return ticker, None

    # Per-cycle provider cache: at most two issuers and a shared SPY result.
    quotes = dict(await asyncio.gather(*(fetch(ticker) for ticker in sorted(symbols))))
    seen = as_utc(now) if now is not None else datetime.now(UTC)
    writes = 0
    status_counts = {}
    for row, window in events:
        ticker, spy = quotes.get(row['ticker']), quotes.get(MARKET)
        step = reaction_step(window, seen, dict(row), ticker or [], spy or [],
                             provider_unavailable=row['ticker'] in symbols and (ticker is None or spy is None))
        result = await pool.execute('''INSERT INTO official_event_reaction
            (event_id,known_at,session_date,observed_at,next_check_at,timing,status,gap,anchor,
             follow_through,gap_reason,follow_reason)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9::jsonb,$10::jsonb,$11,$12)
            ON CONFLICT (event_id) DO UPDATE SET observed_at=EXCLUDED.observed_at,next_check_at=EXCLUDED.next_check_at,
                status=EXCLUDED.status,gap=EXCLUDED.gap,anchor=EXCLUDED.anchor,follow_through=EXCLUDED.follow_through,
                gap_reason=EXCLUDED.gap_reason,follow_reason=EXCLUDED.follow_reason
            WHERE official_event_reaction.status='pending' AND official_event_reaction.observed_at=$13
              AND official_event_reaction.observed_at < EXCLUDED.observed_at''',
            row['id'], window.known, window.session, seen, step['next_check_at'], window.timing, step['status'],
            *(json.dumps(step[k], allow_nan=False) if step[k] is not None else None
              for k in ('gap', 'anchor', 'follow_through')), step['gap_reason'], step['follow_reason'],
            row['previous_observed_at'])
        if result.endswith(' 1'):
            writes += 1
            state = step['status']
            status_counts[state] = status_counts.get(state, 0) + 1
    return {'ok': True, 'events_checked': len(events), 'events_written': writes,
            'symbols_read': len(quotes), 'statuses': status_counts}
