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
    max_wait = float(os.environ.get("BACKFILL_MAX_WAIT", "120"))
    ids = await store.unsubmitted_alpha_ids_missing_official(pool, user_id, limit=limit)
    print(f"backfill target: {len(ids)} unsubmitted alphas missing official self-corr",
          flush=True)

    client = BrainClient(creds[0], creds[1])
    updated = miss = 0
    try:
        await client.authenticate()

        diag = os.environ.get("BACKFILL_DIAG", "").strip()
        if diag:
            # Evidence mode: get_self_correlation returns a bare None for THREE very
            # different causes (still-computing timeout / 200 whose body has no `max`
            # / non-2xx we swallow). Dump the raw exchange so we can tell them apart
            # instead of guessing at the fix.
            import time as _time
            for aid in [a.strip() for a in diag.split(",") if a.strip()]:
                print(f"\n===== DIAG {aid} =====", flush=True)
                t0 = _time.monotonic()
                for i in range(1, 41):  # up to ~200s at 5s intervals
                    r = await client._client.get(f"/alphas/{aid}/correlations/self")
                    body = (r.text or "").strip()
                    print(
                        f"[{i:02d}] t={_time.monotonic()-t0:6.1f}s "
                        f"status={r.status_code} len={len(body)} "
                        f"retry-after={r.headers.get('Retry-After')!r} "
                        f"body[:200]={body[:200]!r}",
                        flush=True,
                    )
                    if r.status_code == 200 and body:
                        print(f"  -> TERMINAL 200 with body after "
                              f"{_time.monotonic()-t0:.1f}s", flush=True)
                        break
                    if r.status_code not in (200, 202):
                        print(f"  -> NON-2xx {r.status_code} (swallowed as None "
                              f"by get_self_correlation)", flush=True)
                        break
                    await asyncio.sleep(5.0)
            return 0
        for i, aid in enumerate(ids, 1):
            # BRAIN computes self-corr LAZILY: our GET is what TRIGGERS the compute
            # for a cold alpha, and it answers 202/empty-200 until it finishes. The
            # old 30s ceiling was calibrated on an already-computed alpha (<=10s) and
            # so timed out on every cold one — 2026-07-13 backfill: 1/15, the single
            # success being the one BRAIN had already cached, the other 14 each
            # burning exactly 30.0s. Default to the client's own 120s budget;
            # BACKFILL_MAX_WAIT tunes it without another code change.
            v = await client.get_self_correlation(aid, max_wait_s=max_wait)
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
