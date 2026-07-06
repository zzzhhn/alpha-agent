"""One-off diagnostic: dump the RAW shape of an alpha's in-sample checks and its
/correlations/self response.

The miner's OFFICIAL self-correlation column comes back None for passed/flagged
rows. The value clearly exists on the platform, so our parse is wrong or the
endpoint needs different handling. This prints the real JSON structure of a few
of the user's alphas (is.checks each in full + the /correlations/self body) so
the parser can be fixed against ground truth instead of a guess. No sim work.

Env: BRAIN_USERNAME/BRAIN_PASSWORD (preferred) or DATABASE_URL (+ BYOK_MASTER_KEY).
"""
import asyncio
import json
import os
import sys


async def _load_creds():
    env_user = os.environ.get("BRAIN_USERNAME")
    env_pass = os.environ.get("BRAIN_PASSWORD")
    if env_user and env_pass:
        return (env_user, env_pass), None
    import asyncpg

    from alpha_agent.brain import vault

    pool = await asyncpg.create_pool(os.environ["DATABASE_URL"], min_size=1, max_size=2)
    uid = os.environ.get("BRAIN_MINING_USER_ID")
    if uid:
        user_id = int(uid)
    else:
        row = await pool.fetchrow(
            "SELECT user_id FROM user_byok WHERE provider='worldquant_brain' "
            "ORDER BY encrypted_at DESC LIMIT 1"
        )
        user_id = row["user_id"] if row else None
    creds = await vault.load_brain_credentials(pool, user_id) if user_id else None
    return creds, pool


async def _dump_corr(c, aid: str) -> None:
    """Poll /correlations/self past 202 and print the full body + its keys."""
    for _ in range(8):
        r = await c.get(f"/alphas/{aid}/correlations/self")
        if r.status_code == 202:
            await asyncio.sleep(3.0)
            continue
        print(f"  corr/self status={r.status_code}", flush=True)
        if r.status_code == 200:
            body = r.json()
            if isinstance(body, dict):
                print(f"  corr/self TOP-LEVEL KEYS: {sorted(body.keys())}", flush=True)
                for k in ("max", "min", "self", "prod"):
                    if k in body:
                        print(f"    body[{k!r}] = {json.dumps(body[k])[:200]}", flush=True)
            print(f"  corr/self BODY[:1200]: {json.dumps(body)[:1200]}", flush=True)
        return


async def _main() -> int:
    from alpha_agent.brain.client import BrainClient

    creds, pool = await _load_creds()
    if not creds:
        print("no BRAIN credentials", flush=True)
        return 1
    client = BrainClient(creds[0], creds[1])
    try:
        await client.authenticate()
        c = client._client
        r = await c.get("/users/self/alphas", params={"limit": 6, "offset": 0})
        results = r.json().get("results", []) if r.status_code == 200 else []
        print(f"=== user has >= {len(results)} alphas (inspecting up to 3) ===", flush=True)
        for a in results[:3]:
            aid = a.get("id")
            print(f"\n### ALPHA {aid} status={a.get('status')} grade={a.get('grade')} ###",
                  flush=True)
            isb = a.get("is") or {}
            print(f"  is TOP-LEVEL KEYS: {sorted(isb.keys())}", flush=True)
            # Any self-correlation-ish scalar directly on the is block?
            for k in isb:
                if "corr" in k.lower():
                    print(f"    is[{k!r}] = {json.dumps(isb[k])[:200]}", flush=True)
            for chk in (isb.get("checks") or []):
                name = chk.get("name", "")
                if "CORR" in name.upper() or "SELF" in name.upper():
                    print(f"  SELF-CORR CHECK (full): {json.dumps(chk)}", flush=True)
                else:
                    print(f"  check {name}: keys={sorted(chk.keys())}", flush=True)
            await _dump_corr(c, aid)
    finally:
        await client.aclose()
        if pool:
            await pool.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
