"""Calendar-based due slots, independent of GitHub cron arrival time."""
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException

from alpha_agent.data.capacity import read_capacity
from alpha_agent.paper import bot_store as store
from alpha_agent.paper.bot_models import BotConfig
from alpha_agent.paper.market_clock import as_utc, market_session, target_slot_times


async def enqueue_due(pool, now=None):
    now = now or datetime.now(UTC)
    market = market_session(now)
    if not market['is_open']:
        return {'enqueued': 0, 'reason': 'market_closed'}
    if not (await read_capacity(pool))['allow_writes']:
        return {'enqueued': 0, 'reason': 'storage_headroom_low'}
    rows = await pool.fetch("SELECT a.id,a.user_id,c.config FROM sim_account a JOIN sim_bot_config c ON c.account_id=a.id WHERE a.kind='bot' AND a.status='active' AND c.config->>'schedule_enabled'='true' ORDER BY a.id LIMIT 20")
    slots = target_slot_times(now)
    count, skipped = 0, []
    for row in rows:
        config = BotConfig.model_validate(store.unpack(row['config']))
        for slot, enabled in [('open_after', config.open_enabled), ('close_before', config.close_enabled)]:
            due = as_utc(slots[slot])
            if enabled and due <= now < due + timedelta(minutes=20):
                try:
                    await store.enqueue(pool, row['user_id'], row['id'], trigger=slot,
                                        slot_key=f"{row['id']}:{slots['session_date']}:{slot}", now=now)
                    count += 1
                except HTTPException as exc:
                    skipped.append({'account_id': row['id'], 'reason': exc.detail})
    return {'enqueued': count, 'skipped': skipped}
