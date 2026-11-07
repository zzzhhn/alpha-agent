"""Raw-price bot valuation, separate from human daily-close execution.

Only latest marks and one daily sample are persisted, never a minute-bar feed.
Provider reads happen before the short account-locked write transaction.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta
from math import isfinite
from typing import Any

from alpha_agent.market_session import _xnys_calendar, latest_completed_xnys_session
from alpha_agent.paper.intraday import fetch_bars
from alpha_agent.paper.market_clock import as_utc, market_session

MAX_SYMBOLS = 21  # Up to 20 held instruments plus raw-price SPY.
FETCH_CONCURRENCY = 2
FETCH_BUDGET_SECONDS = 240


def valuation_session(now: datetime) -> dict:
    current = market_session(now)
    if current['is_open']:
        return current
    day = latest_completed_xnys_session(now)
    calendar = _xnys_calendar()
    session = calendar.date_to_session(day)
    return {
        'session_date': day.isoformat(), 'is_open': False,
        'open_at': calendar.session_open(session).to_pydatetime().isoformat(),
        'close_at': calendar.session_close(session).to_pydatetime().isoformat(),
    }


def effective_mark(position: dict, now: datetime) -> dict:
    """Recheck stored marks for freshness without inventing a replacement price."""
    price, at = position.get('mark_price'), position.get('mark_at')
    quality = position.get('price_quality') or 'missing'
    if quality == 'corporate_action_blocked':
        try:
            at = as_utc(at) if at is not None else None
        except ValueError:
            at = None
        return {'price': None, 'as_of': at, 'quality': quality}
    try:
        price, at = float(price), as_utc(at)
        if not isfinite(price) or price <= 0 or at > now:
            raise ValueError('invalid mark')
    except (TypeError, ValueError):
        return {'price': None, 'as_of': None, 'quality': 'missing'}
    session = valuation_session(now)
    opening, closing = as_utc(session['open_at']), as_utc(session['close_at'])
    if at < opening or at > closing:
        quality = 'stale'
    elif session['is_open']:
        quality = 'fresh' if now - at <= timedelta(minutes=5) else 'stale'
    else:
        quality = 'session_close' if at == closing else 'stale'
    return {'price': price, 'as_of': at, 'quality': quality}


def summarize_marks(positions: list[dict], cash: float, now: datetime) -> dict:
    live = [dict(row) for row in positions if row['qty'] > 0]
    marks = {row['ticker']: effective_mark(row, now) for row in live}
    qualities = {mark['quality'] for mark in marks.values()}
    complete = qualities.issubset({'fresh', 'session_close'})
    quality = ('cash_only' if not live else 'corporate_action_blocked'
               if 'corporate_action_blocked' in qualities else 'partial'
               if not complete else 'fresh' if 'fresh' in qualities else 'session_close')
    value = float(cash) + sum(marks[row['ticker']]['price'] * row['qty'] for row in live) if complete else None
    unrealized = sum((marks[row['ticker']]['price'] - row['avg_cost']) * row['qty'] for row in live) if complete else None
    dates = [mark['as_of'] for mark in marks.values() if mark['as_of'] is not None]
    return {
        'marks': marks, 'portfolio_value': value, 'unrealized_pnl': unrealized,
        'valuation_quality': quality, 'valued_at': min(dates) if dates and complete else now if not live else None,
    }


async def last_valid_valuation(pool: Any, account: dict, now: datetime) -> dict | None:
    """Historical display only. Never substitute these values into execution."""
    row = await pool.fetchrow(
        'SELECT portfolio_value,unrealized_pnl,valued_at,as_of_date,valuation_quality '
        'FROM sim_equity_daily WHERE account_id=$1 AND cohort_id=$2 '
        'AND portfolio_value IS NOT NULL AND unrealized_pnl IS NOT NULL '
        "AND valuation_quality IN ('fresh','session_close','cash_only') "
        'AND valued_at <= $3 ORDER BY as_of_date DESC LIMIT 1',
        account['id'], account['reset_count'], now,
    )
    if row is None:
        return None
    initial = account['initial_cash']
    return {
        'portfolio_value': row['portfolio_value'], 'unrealized_pnl': row['unrealized_pnl'],
        'total_return_pct': (row['portfolio_value'] / initial - 1) * 100 if initial > 0 else None,
        'valued_at': row['valued_at'].isoformat(), 'market_date': row['as_of_date'].isoformat(),
        'valuation_quality': row['valuation_quality'],
    }


def _latest_mark(bars: list[dict], now: datetime, session: dict) -> dict:
    candidates = []
    opening, closing = as_utc(session['open_at']), as_utc(session['close_at'])
    for bar in bars:
        try:
            start, end, fetched = (as_utc(bar[key]) for key in ('start', 'end', 'fetched_at'))
            price = float(bar['close'])
        except (KeyError, TypeError, ValueError):
            continue
        if not (opening <= start < end <= min(now, closing) and end <= fetched <= now):
            continue
        if not isfinite(price) or price <= 0:
            continue
        candidates.append((end, price, bar))
    if not candidates:
        return {'mark_price': None, 'mark_at': None, 'price_quality': 'missing'}
    end, price, bar = max(candidates, key=lambda item: item[0])
    if (bar.get('price_basis') != 'raw_unadjusted' or not bar.get('source')
            or bar.get('corporate_actions_known') is not True
            or bar.get('corporate_actions') or bar.get('dividends') not in (0, 0.0)
            or bar.get('stock_splits') not in (0, 0.0)):
        return {'mark_price': None, 'mark_at': end, 'price_quality': 'corporate_action_blocked'}
    return {'mark_price': price, 'mark_at': end,
            'price_quality': 'fresh' if session['is_open'] and now - end <= timedelta(minutes=5)
            else 'session_close' if end == closing else 'stale'}


async def refresh_marks(
    pool: Any, account_id: int, now: datetime | str | None = None, *,
    _cache: dict | None = None,
) -> dict:
    """Refresh one bot book and upsert its NY-session sample, even without orders.

    At most 21 unique symbols including SPY per round; callers may share the
    private cache across a bounded daily batch. A missing/stale/action-blocked
    mark makes NAV and unrealized PnL null. Cash, cost and realized facts remain.
    Network errors are summarized by type only, without credential/error dumps.
    """
    instant = as_utc(now) if now is not None else datetime.now(UTC)
    session = valuation_session(instant)
    account = await pool.fetchrow("SELECT * FROM sim_account WHERE id=$1 AND kind='bot'", account_id)
    if account is None:
        raise ValueError('bot account not found')
    cohort = account['reset_count']
    positions = await pool.fetch(
        'SELECT * FROM sim_position WHERE account_id=$1 AND cohort_id=$2 AND qty>0 ORDER BY ticker',
        account_id, cohort,
    )
    cache = _cache if _cache is not None else {}
    errors = {}
    symbols = list(dict.fromkeys(['SPY'] + [row['ticker'] for row in positions]))
    quote_asof = instant if session['is_open'] else as_utc(session['close_at'])
    scheduled = []
    for ticker in symbols:
        key = (session['session_date'], ticker)
        if key in cache:
            continue
        if len(cache) + len(scheduled) >= MAX_SYMBOLS:
            errors[ticker] = 'symbol_budget_exceeded'
            continue
        scheduled.append((ticker, key))
    semaphore = asyncio.Semaphore(FETCH_CONCURRENCY)

    async def fetch_one(ticker, key):
        try:
            async with semaphore:
                bars = await fetch_bars(ticker, now=quote_asof)
            # Production fetch timestamps are actual acquisition instants. An
            # explicit injected now remains the as-of boundary in tests/replay.
            checked_at = instant if now is not None else datetime.now(UTC)
            cache[key] = _latest_mark(bars, checked_at, session)
        except Exception as exc:
            errors[ticker] = type(exc).__name__
            cache[key] = {'mark_price': None, 'mark_at': None, 'price_quality': 'missing'}

    try:
        async with asyncio.timeout(FETCH_BUDGET_SECONDS):
            await asyncio.gather(*(fetch_one(ticker, key) for ticker, key in scheduled))
    except TimeoutError:
        for ticker, key in scheduled:
            if key not in cache:
                errors[ticker] = 'fetch_budget_exceeded'
                cache[key] = {'mark_price': None, 'mark_at': None, 'price_quality': 'missing'}

    if now is None:
        instant = datetime.now(UTC)

    # Network has finished. Lock then reread quantities/cash: concurrent fills
    # must not be overwritten by the initial pre-fetch account snapshot.
    async with pool.acquire() as conn:
        async with conn.transaction():
            account = await conn.fetchrow(
                "SELECT * FROM sim_account WHERE id=$1 AND kind='bot' FOR UPDATE", account_id,
            )
            if account is None or account['reset_count'] != cohort:
                return {'account_id': account_id, 'valuation_quality': 'cohort_changed', 'errors': errors}
            current = await conn.fetch(
                'SELECT * FROM sim_position WHERE account_id=$1 AND cohort_id=$2 ORDER BY ticker',
                account_id, cohort,
            )
            updated = []
            for row in current:
                position = dict(row)
                if position['qty'] > 0:
                    mark = cache.get((session['session_date'], position['ticker']), {
                        'mark_price': None, 'mark_at': None, 'price_quality': 'missing',
                    })
                    # Unknown corporate action freezes this instrument until
                    # an explicit reconciliation clears the persisted flag.
                    if position.get('price_quality') == 'corporate_action_blocked':
                        mark = {'mark_price': None, 'mark_at': position.get('mark_at'),
                                'price_quality': 'corporate_action_blocked'}
                    elif mark['price_quality'] != 'corporate_action_blocked':
                        previous = effective_mark(position, instant)
                        # A slower refresh must not replace a newer mark from
                        # a concurrent fill/refresh with older or absent data.
                        if (previous['as_of'] is not None and previous['price'] is not None
                                and (mark['mark_at'] is None or previous['as_of'] > mark['mark_at'])):
                            mark = {'mark_price': previous['price'], 'mark_at': previous['as_of'],
                                    'price_quality': previous['quality']}
                    position.update(mark)
                    await conn.execute(
                        'UPDATE sim_position SET mark_price=$1,mark_at=$2,price_quality=$3 '
                        'WHERE account_id=$4 AND cohort_id=$5 AND ticker=$6',
                        mark['mark_price'], mark['mark_at'], mark['price_quality'],
                        account_id, cohort, position['ticker'],
                    )
                updated.append(position)
            summary = summarize_marks(updated, account['cash'], instant)
            spy = cache.get((session['session_date'], 'SPY'), {})
            benchmark = effective_mark(spy, instant)
            benchmark_close = benchmark['price'] if benchmark['quality'] in {'fresh', 'session_close'} else None
            created_at = account.get('created_at')
            if created_at is not None and as_utc(created_at) > as_utc(session['close_at']):
                # Before this account's first market session, an older SPY
                # close cannot date a portfolio history that did not exist.
                return {'account_id': account_id, 'session_date': session['session_date'],
                        'portfolio_value': summary['portfolio_value'],
                        'valuation_quality': summary['valuation_quality'],
                        'valued_at': instant.isoformat(), 'benchmark_close': None,
                        'benchmark_quality': 'before_account_creation',
                        'sample_written': False, 'errors': errors}
            await conn.execute(
                'INSERT INTO sim_equity_daily (account_id,cohort_id,as_of_date,portfolio_value,cash,'
                'unrealized_pnl,realized_pnl,benchmark_close,valuation_quality,valued_at) '
                'VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10) '
                'ON CONFLICT (account_id,cohort_id,as_of_date) DO UPDATE SET '
                'portfolio_value=EXCLUDED.portfolio_value,cash=EXCLUDED.cash,'
                'unrealized_pnl=EXCLUDED.unrealized_pnl,realized_pnl=EXCLUDED.realized_pnl,'
                'benchmark_close=EXCLUDED.benchmark_close,valuation_quality=EXCLUDED.valuation_quality,'
                'valued_at=EXCLUDED.valued_at '
                'WHERE (sim_equity_daily.valued_at IS NULL OR EXCLUDED.valued_at >= sim_equity_daily.valued_at) '
                'AND (EXCLUDED.portfolio_value IS NOT NULL OR sim_equity_daily.portfolio_value IS NULL)',
                account_id, cohort, date.fromisoformat(session['session_date']), summary['portfolio_value'],
                account['cash'], summary['unrealized_pnl'], sum(row['realized_pnl'] or 0 for row in updated),
                benchmark_close, summary['valuation_quality'], instant,
            )
    summary['valued_at'] = summary['valued_at'].isoformat() if summary['valued_at'] else None
    summary['marks'] = {ticker: {**mark, 'as_of': mark['as_of'].isoformat() if mark['as_of'] else None}
                        for ticker, mark in summary['marks'].items()}
    return {'account_id': account_id, 'session_date': session['session_date'], **summary,
            'benchmark_close': benchmark_close, 'benchmark_quality': benchmark['quality'], 'errors': errors}


async def refresh_daily_valuations(
    pool: Any, now: datetime | str | None = None, limit: int = 10, offset: int = 0,
) -> dict:
    """Bounded daily hook; does not depend on any pending order being present."""
    batch_limit = min(max(limit, 1), 10)
    rows = await pool.fetch(
        "SELECT id FROM sim_account WHERE kind='bot' ORDER BY id LIMIT $1 OFFSET $2",
        batch_limit + 1, max(offset, 0),
    )
    has_more = len(rows) > batch_limit
    rows = rows[:batch_limit]
    cache, results = {}, []
    try:
        async with asyncio.timeout(FETCH_BUDGET_SECONDS):
            for row in rows:
                try:
                    result = await refresh_marks(pool, row['id'], now, _cache=cache)
                    results.append({key: result.get(key) for key in ('account_id', 'session_date', 'valuation_quality', 'errors')})
                except Exception as exc:
                    results.append({'account_id': row['id'], 'valuation_quality': 'failed', 'error': type(exc).__name__})
    except TimeoutError:
        done = {result['account_id'] for result in results}
        results.extend({'account_id': row['id'], 'valuation_quality': 'failed', 'error': 'batch_budget_exceeded'}
                       for row in rows if row['id'] not in done)
    return {'accounts': results, 'symbols_read': len(cache), 'symbol_limit': MAX_SYMBOLS,
            'has_more_accounts': has_more, 'next_offset': offset + batch_limit if has_more else None}
