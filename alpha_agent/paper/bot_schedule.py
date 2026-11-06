"""Calendar-based due slots, independent of GitHub cron arrival time."""
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException

from alpha_agent.data.capacity import read_capacity
from alpha_agent.paper import bot_store as store
from alpha_agent.paper.bot_models import BotConfig
from alpha_agent.paper.market_clock import NEW_YORK, as_utc, market_session, target_slot_times


def schedule_observations(config, recorded, now=None, *, scheduled_runs=()):
    """Overlay bounded expected slots without pretending a worker observed them.

    Reads never enqueue or backfill trades. Only the current configuration's
    lifetime is inferred; actual older observations remain authoritative.
    """
    now = now or datetime.now(UTC)
    rows = {(str(r['session_date']), r['slot']): dict(r) for r in recorded}
    # enqueue commits before its observation write. The run is authoritative
    # if a carrier died between these two writes.
    for run in scheduled_runs:
        key = (str(run['trading_session']), run['trigger'])
        slots = target_slot_times(run['created_at'])
        rows[key] = {
            'session_date': key[0], 'slot': key[1], 'planned_at': as_utc(slots[key[1]]),
            'observed_at': run['created_at'], 'status': run.get('status', 'enqueued'), 'reason': None,
            'finished_at': run.get('finished_at'),
            'run_id': str(run['id']),
        }
    activated = config.get('config_updated_at')
    if config['schedule_enabled'] and activated:
        for days_ago in range(8):
            slots = target_slot_times(now - timedelta(days=days_ago))
            for slot, enabled in [('open_after', config['open_enabled']), ('close_before', config['close_enabled'])]:
                due = as_utc(slots[slot])
                key = (slots['session_date'], slot)
                prior = rows.get(key)
                if not enabled or due < as_utc(activated) or (prior and prior['status'] != 'planned'):
                    continue
                status = 'missed' if now >= due + timedelta(minutes=20) else 'waiting' if now >= due else 'planned'
                rows[key] = {
                    'session_date': slots['session_date'], 'slot': slot, 'planned_at': due,
                    'observed_at': prior['observed_at'] if prior else None,
                    'status': status, 'reason': 'trigger_not_observed' if status != 'planned' else None,
                    'run_id': None, 'inferred': True,
                }
    return sorted(rows.values(), key=lambda row: as_utc(row['planned_at']), reverse=True)[:10]


async def enqueue_due(pool, now=None):
    now = now or datetime.now(UTC)
    market = market_session(now)
    if now.astimezone(NEW_YORK).date().isoformat() != market['session_date']:
        return {'enqueued': 0, 'reason': 'market_closed'}
    capacity = await read_capacity(pool)
    if not capacity['allow_writes']:
        return {'enqueued': 0, 'reason': 'storage_headroom_low'}
    rows = await pool.fetch("SELECT a.id,a.user_id,c.config,c.config_version,c.updated_at FROM sim_account a JOIN sim_bot_config c ON c.account_id=a.id WHERE a.kind='bot' AND a.status='active' AND c.config->>'schedule_enabled'='true' ORDER BY a.id LIMIT 20")
    slots = target_slot_times(now)
    count, missed, skipped = 0, 0, []
    for row in rows:
        config = BotConfig.model_validate(store.unpack(row['config']))
        for slot, enabled in [('open_after', config.open_enabled), ('close_before', config.close_enabled)]:
            due = as_utc(slots[slot])
            if not enabled:
                continue
            # Do not invent a missed obligation predating this configuration.
            if row['updated_at'] > due:
                continue
            status, reason, run_id = 'planned', None, None
            if due <= now < due + timedelta(minutes=20) and market['is_open']:
                try:
                    key = f"{row['id']}:{slots['session_date']}:{slot}"
                    run = await store.enqueue(pool, row['user_id'], row['id'], trigger=slot, slot_key=key, now=now)
                    if run.get('slot_key') == key:
                        status, run_id = 'enqueued', run['id']
                        count += 1
                    else:
                        status, reason = 'blocked', 'run_active'
                except HTTPException as exc:
                    status = 'blocked'
                    reason = {429: 'daily_limit', 400: 'credential_missing', 409: 'account_unavailable'}.get(exc.status_code, 'enqueue_failed')
                    skipped.append({'account_id': row['id'], 'reason': reason})
            elif now >= due + timedelta(minutes=20):
                status, reason = 'missed', 'slot_expired'
            written = await record_slot(pool, row, slots, slot, due, now, status, reason, run_id)
            missed += int(written == 'missed')
    return {'enqueued': count, 'observed_accounts': len(rows), 'missed_observations': missed,
            'reason': 'no_enabled_accounts' if not rows else 'slots_checked', 'skipped': skipped}


async def record_slot(pool, account, slots, slot, due, now, status, reason, run_id):
    import uuid
    return await pool.fetchval(
        'INSERT INTO sim_bot_schedule_slot(account_id,session_date,slot,planned_at,observed_at,config_version,status,reason,run_id) '
        'VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9) ON CONFLICT(account_id,session_date,slot) DO UPDATE SET '
        'observed_at=EXCLUDED.observed_at,status=EXCLUDED.status,reason=EXCLUDED.reason,run_id=EXCLUDED.run_id '
        "WHERE sim_bot_schedule_slot.status<>'enqueued' AND (sim_bot_schedule_slot.status<>EXCLUDED.status OR sim_bot_schedule_slot.reason IS DISTINCT FROM EXCLUDED.reason) RETURNING status",
        account['id'], datetime.fromisoformat(slots['session_date']).date(), slot, due, now,
        account['config_version'], status, reason, uuid.UUID(run_id) if run_id else None)
