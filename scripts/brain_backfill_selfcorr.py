"""Backfill BRAIN's OFFICIAL self-correlation for mined alphas recorded before the
get_self_correlation empty-200 poll fix (they stored None → UI showed 待定).

For each of the user's not-yet-submitted mined alphas that still lacks an official
self-corr, re-fetch it via the now-fixed endpoint (polls through 202 + empty-200)
and write it to brain_alphas.self_correlation. Bounded per-call wait so a whole
batch stays inside the Action's timeout. No simulation work.

Env: DATABASE_URL (+ BYOK_MASTER_KEY) or BRAIN_USERNAME/BRAIN_PASSWORD;
optional BRAIN_MINING_USER_ID, BACKFILL_LIMIT.
"""
import asyncio
import os
import sys


async def _load():
    """Return (creds, pool, user_id). Creds from BYOK vault (needs the DB) or env."""
    import asyncpg

    pool = await asyncpg.create_pool(
        os.environ["DATABASE_URL"], min_size=1, max_size=2
    )
    uid = os.environ.get("BRAIN_MINING_USER_ID")
    if uid:
        user_id = int(uid)
    else:
        row = await pool.fetchrow(
            "SELECT user_id FROM user_byok WHERE provider='worldquant_brain' "
            "ORDER BY encrypted_at DESC LIMIT 1"
        )
        user_id = row["user_id"] if row else None
    env_user = os.environ.get("BRAIN_USERNAME")
    env_pass = os.environ.get("BRAIN_PASSWORD")
    if env_user and env_pass:
        return (env_user, env_pass), pool, user_id
    from alpha_agent.brain import vault

    creds = await vault.load_brain_credentials(pool, user_id) if user_id else None
    return creds, pool, user_id


async def _main() -> int:
    from alpha_agent.brain import store
    from alpha_agent.brain.client import BrainClient

    creds, pool, user_id = await _load()
    if not creds or user_id is None:
        print("no BRAIN credentials / user_id", flush=True)
        return 1
    limit = int(os.environ.get("BACKFILL_LIMIT", "120"))
    ids = await store.unsubmitted_alpha_ids_missing_official(pool, user_id, limit=limit)
    print(f"backfill target: {len(ids)} unsubmitted alphas missing official self-corr",
          flush=True)

    client = BrainClient(creds[0], creds[1])
    updated = miss = 0
    try:
        await client.authenticate()
        for i, aid in enumerate(ids, 1):
            # 30s per call: the empty-200 phase resolved in <=10s in diagnostics,
            # so this is ample without letting one slow alpha stall the batch.
            v = await client.get_self_correlation(aid, max_wait_s=30.0)
            if v is None:
                miss += 1
                print(f"[{i}/{len(ids)}] {aid} → still None", flush=True)
                continue
            await store.update_official_self_correlation(pool, user_id, aid, value=v)
            updated += 1
            print(f"[{i}/{len(ids)}] {aid} → {v:.4f} ✅", flush=True)
    finally:
        await client.aclose()
        await pool.close()
    print(f"\nDONE: updated={updated} still_none={miss} of {len(ids)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
