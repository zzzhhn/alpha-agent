"""Low-frequency marks only: no decisions, orders, minute-bar storage or BYOK."""
from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta

from alpha_agent.data.capacity import read_capacity
from alpha_agent.paper.bot_valuation import MAX_SYMBOLS, refresh_marks
from alpha_agent.paper.market_clock import as_utc, market_session

JOB = 'paper_bot_valuation'
INTERVAL_MINUTES = 30
ACCOUNT_LIMIT = 10
BUDGET_SECONDS = 120


def refresh_slot(now: datetime) -> datetime | None:
    session = market_session(now)
    opening, closing = as_utc(session['open_at']), as_utc(session['close_at'])
    if not opening <= now < closing + timedelta(minutes=15):
        return None
    # Include one post-close observation, respecting shortened sessions and DST.
    if now >= closing:
        return closing
    return opening + timedelta(minutes=int((now - opening).total_seconds() // 1800) * 30)


async def claim_refresh(pool, slot: datetime, now: datetime) -> int | None:
    """One reusable status row, short transaction; no connection held during I/O."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.fetchval('SELECT pg_advisory_xact_lock(hashtext($1))', JOB)
            previous = await conn.fetchrow(
                'SELECT id,started_at FROM cron_runs WHERE cron_name=$1 ORDER BY started_at DESC LIMIT 1', JOB)
            if previous and (previous['started_at'] >= slot or now - previous['started_at'] < timedelta(minutes=25)):
                return None
            details = json.dumps({'slot': slot.isoformat(), 'state': 'running'})
            if previous:
                await conn.execute(
                    'UPDATE cron_runs SET started_at=$2,finished_at=NULL,ok=NULL,error_count=0,details=$3::jsonb WHERE id=$1',
                    previous['id'], now, details)
                return previous['id']
            return await conn.fetchval(
                'INSERT INTO cron_runs(cron_name,started_at,details) VALUES($1,$2,$3::jsonb) RETURNING id',
                JOB, now, details)


async def refresh_intraday_valuations(pool, now: datetime | None = None) -> dict:
    instant = now or datetime.now(UTC)
    slot = refresh_slot(instant)
    if slot is None:
        return {'ok': True, 'reason': 'outside_refresh_window', 'symbols_read': 0}
    if not (await read_capacity(pool))['allow_writes']:
        return {'ok': True, 'reason': 'storage_headroom_low', 'symbols_read': 0}
    claim = await claim_refresh(pool, slot, instant)
    if claim is None:
        return {'ok': True, 'reason': 'already_checked', 'symbols_read': 0}
    result = {'ok': True, 'reason': 'refreshed', 'interval_minutes': INTERVAL_MINUTES,
              'attempted_accounts': 0, 'updated_accounts': 0, 'deferred_accounts': 0,
              'symbols_read': 0, 'symbol_limit': MAX_SYMBOLS, 'quality_counts': {}, 'error_count': 0}
    cache = {}
    try:
        # Oldest observed books first; accounts beyond the shared symbol budget
        # are deferred rather than partially rewritten with unavailable quotes.
        rows = await pool.fetch(
            "SELECT a.id,array_agg(p.ticker ORDER BY p.ticker) AS tickers FROM sim_account a "
            'JOIN sim_position p ON p.account_id=a.id AND p.cohort_id=a.reset_count AND p.qty>0 '
            "WHERE a.kind='bot' AND a.status='active' "
            "AND NOT EXISTS(SELECT 1 FROM sim_bot_run r WHERE r.account_id=a.id AND r.status IN ('queued','running')) "
            'GROUP BY a.id ORDER BY (SELECT max(e.valued_at) FROM sim_equity_daily e '
            'WHERE e.account_id=a.id AND e.cohort_id=a.reset_count) ASC NULLS FIRST,a.id LIMIT $1', ACCOUNT_LIMIT)
        session_date = market_session(instant)['session_date']
        async with asyncio.timeout(BUDGET_SECONDS):
            for row in rows:
                needed = {(session_date, ticker) for ticker in ['SPY', *row['tickers']]}
                if len(set(cache) | needed) > MAX_SYMBOLS:
                    result['deferred_accounts'] += 1
                    continue
                result['attempted_accounts'] += 1
                try:
                    valuation = await refresh_marks(pool, row['id'], now, _cache=cache)
                    quality = valuation['valuation_quality']
                    result['quality_counts'][quality] = result['quality_counts'].get(quality, 0) + 1
                    result['updated_accounts'] += int(quality in {'fresh', 'session_close', 'cash_only'})
                    result['error_count'] += len(valuation.get('errors', {}))
                except Exception:
                    result['error_count'] += 1
    except TimeoutError:
        result.update(reason='refresh_budget_exhausted', error_count=result['error_count'] + 1)
    except Exception:
        result.update(reason='refresh_failed', error_count=result['error_count'] + 1)
    result['symbols_read'] = len(cache)
    result['ok'] = result['error_count'] == 0
    await pool.execute(
        'UPDATE cron_runs SET finished_at=now(),ok=$2,error_count=$3,details=$4::jsonb WHERE id=$1',
        claim, result['ok'], result['error_count'], json.dumps({'slot': slot.isoformat(), **result}))
    return result
