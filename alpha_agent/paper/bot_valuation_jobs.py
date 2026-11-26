"""Durable daily bot valuation queue with per-book leases."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from alpha_agent.market_session import _xnys_calendar, next_xnys_session
from alpha_agent.paper.market_clock import as_utc

LEASE_DURATION = timedelta(minutes=5)


@dataclass(frozen=True)
class DailyValuationClaim:
    session_date: date
    account_id: int
    cohort_id: int
    token: UUID
    next_open: datetime

    async def lock(self, conn: Any, now: datetime) -> bool:
        return bool(await conn.fetchval(
            "SELECT true FROM sim_bot_valuation_job WHERE session_date=$1 AND account_id=$2 "
            "AND cohort_id=$3 AND claim_token=$4 AND status='running' AND lease_until>$5 FOR UPDATE",
            self.session_date, self.account_id, self.cohort_id, self.token, now,
        ))

    async def finish(
        self, conn: Any, status: str, reason: str | None = None, quality: str | None = None,
    ) -> bool:
        return bool(await conn.fetchval(
            "UPDATE sim_bot_valuation_job SET status=$5, reason=$6, valuation_quality=$7, "
            "claim_token=NULL,lease_until=NULL,updated_at=now() WHERE session_date=$1 AND account_id=$2 "
            "AND cohort_id=$3 AND claim_token=$4 AND status='running' RETURNING true",
            self.session_date, self.account_id, self.cohort_id, self.token, status, reason, quality,
        ))


async def _seed_jobs(pool: Any, day: date, close: datetime) -> None:
    # Today's current book cannot be used to reconstruct a missed prior close.
    await pool.execute(
        "UPDATE sim_bot_valuation_job SET status='skipped',reason='session_advanced',"
        "claim_token=NULL,lease_until=NULL,updated_at=now() WHERE session_date<$1 "
        "AND status IN ('pending','running','deferred')", day,
    )
    await pool.execute(
        "INSERT INTO sim_bot_valuation_job(session_date,account_id,cohort_id,status,reason) "
        "SELECT $1,id,reset_count,CASE WHEN status='disabled' THEN 'skipped' ELSE 'pending' END, "
        "CASE WHEN status='disabled' THEN 'account_disabled' END FROM sim_account "
        "WHERE kind='bot' AND COALESCE(reset_at,created_at)<=$2 "
        "ON CONFLICT DO NOTHING", day, close,
    )


async def _claim_job(
    pool: Any, day: date, now: datetime, next_open: datetime, attempted: list[int],
) -> DailyValuationClaim | None:
    token = uuid4()
    row = await pool.fetchrow(
        "WITH next_job AS ("
        "SELECT account_id,cohort_id FROM sim_bot_valuation_job WHERE session_date=$1 "
        "AND account_id<>ALL($2::bigint[]) AND status IN ('pending','deferred','running') "
        "AND (status<>'running' OR lease_until<=$3) "
        "ORDER BY attempts,updated_at,account_id,cohort_id LIMIT 1 FOR UPDATE SKIP LOCKED"
        ") UPDATE sim_bot_valuation_job job SET status='running',claim_token=$4,"
        "lease_until=$5,attempts=job.attempts+1,updated_at=now() FROM next_job "
        "WHERE job.session_date=$1 AND job.account_id=next_job.account_id "
        "AND job.cohort_id=next_job.cohort_id RETURNING job.account_id,job.cohort_id",
        day, attempted, now, token, now + LEASE_DURATION,
    )
    return DailyValuationClaim(day, row['account_id'], row['cohort_id'], token, next_open) if row else None


async def run_daily_valuation_jobs(
    pool: Any, now: datetime | str | None = None, limit: int = 10,
) -> dict:
    from alpha_agent.paper import bot_valuation as valuation

    instant = as_utc(now) if now is not None else datetime.now(UTC)
    session = valuation.valuation_session(instant)
    day = date.fromisoformat(session['session_date'])
    cache, results, attempted = {}, [], []
    result = {'accounts': results, 'session_date': day.isoformat(),
              'symbols_read': 0, 'symbol_limit': valuation.MAX_SYMBOLS, 'has_more_accounts': False}
    if session['is_open']:
        return {**result, 'reason': 'market_open'}

    next_open = _xnys_calendar().session_open(next_xnys_session(day)).to_pydatetime()
    await _seed_jobs(pool, day, as_utc(session['close_at']))
    active_claim = None
    try:
        async with asyncio.timeout(valuation.FETCH_BUDGET_SECONDS):
            for _ in range(min(max(limit, 1), 10)):
                claimed_at = instant if now is not None else datetime.now(UTC)
                if claimed_at >= next_open:
                    break
                active_claim = await _claim_job(pool, day, claimed_at, next_open, attempted)
                if active_claim is None:
                    break
                attempted.append(active_claim.account_id)
                try:
                    outcome = await valuation.refresh_marks(
                        pool, active_claim.account_id, now, _cache=cache, _daily_claim=active_claim,
                    )
                except Exception as exc:
                    outcome = {'job_status': 'deferred', 'reason': type(exc).__name__}

                status = outcome.get('job_status', 'completed')
                reason = outcome.get('reason')
                if status not in ('completed', 'superseded'):
                    if not await active_claim.finish(pool, status, reason):
                        status, reason = 'superseded', 'claim_lost'
                results.append({
                    'account_id': active_claim.account_id, 'session_date': day.isoformat(),
                    'status': status, 'reason': reason, 'valuation_quality': outcome.get('valuation_quality'),
                    'errors': outcome.get('errors', {}),
                })
                active_claim = None
    except TimeoutError:
        if active_claim is not None:
            released = await active_claim.finish(pool, 'deferred', 'batch_budget_exceeded')
            if released:
                results.append({
                    'account_id': active_claim.account_id, 'session_date': day.isoformat(),
                    'status': 'deferred', 'reason': 'batch_budget_exceeded', 'valuation_quality': None,
                })
        result['reason'] = 'batch_budget_exceeded'
    result['has_more_accounts'] = await pool.fetchval(
        "SELECT EXISTS (SELECT 1 FROM sim_bot_valuation_job WHERE session_date=$1 "
        "AND status IN ('pending','running','deferred'))", day,
    )
    result['symbols_read'] = len(cache)
    return result
