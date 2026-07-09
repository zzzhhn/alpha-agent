"""Pull the FULL WorldQuant BRAIN vocabulary — all datasets (with usage), all
operators, and sample fields from the datasets the generator does NOT yet mine.
The generator has been stuck on ~6 option fields + ~30 fundamental ratios, so the
'value+options ceiling' is a vocabulary artifact. This dumps what's actually
available so new orthogonal families can be built from real fields. API-only, no
sims. Env: BRAIN_USERNAME/BRAIN_PASSWORD or DATABASE_URL(+BYOK_MASTER_KEY)."""
import asyncio
import os
import sys

REGION, UNIV, DELAY = "USA", "TOP3000", 1


async def _load_creds():
    u, p = os.environ.get("BRAIN_USERNAME"), os.environ.get("BRAIN_PASSWORD")
    if u and p:
        return (u, p), None
    import asyncpg

    from alpha_agent.brain import vault
    pool = await asyncpg.create_pool(os.environ["DATABASE_URL"], min_size=1, max_size=2)
    uid = os.environ.get("BRAIN_MINING_USER_ID")
    user_id = int(uid) if uid else (await pool.fetchrow(
        "SELECT user_id FROM user_byok WHERE provider='worldquant_brain' "
        "ORDER BY encrypted_at DESC LIMIT 1"))["user_id"]
    return (await vault.load_brain_credentials(pool, user_id)), pool


async def _paginate(c, path, base_params, cap=400):
    out, offset = [], 0
    while len(out) < cap:
        for _ in range(4):
            r = await c.get(path, params={**base_params, "limit": 50, "offset": offset})
            if r.status_code == 429:
                await asyncio.sleep(4.0)
                continue
            break
        if r.status_code != 200:
            break
        body = r.json()
        res = body.get("results", []) if isinstance(body, dict) else []
        out.extend(res)
        if len(res) < 50:
            break
        offset += 50
    return out


async def _main() -> int:
    from alpha_agent.brain.client import BrainClient
    creds, pool = await _load_creds()
    if not creds:
        print("no creds")
        return 1
    client = BrainClient(creds[0], creds[1])
    try:
        await client.authenticate()
        c = client._client
        eq = {"instrumentType": "EQUITY", "region": REGION, "universe": UNIV, "delay": DELAY}

        # --- OPERATORS ---
        r = await c.get("/operators")
        ops = r.json() if r.status_code == 200 else []
        ops = ops if isinstance(ops, list) else ops.get("results", [])
        print(f"\n=== OPERATORS ({len(ops)}) ===", flush=True)
        from collections import defaultdict
        bycat = defaultdict(list)
        for o in ops:
            bycat[o.get("category", "?")].append(o.get("name", "?"))
        for cat, names in sorted(bycat.items()):
            print(f"  [{cat}] {', '.join(sorted(names))}", flush=True)

        # --- DATASETS ---
        ds = await _paginate(c, "/data-sets", eq, cap=300)
        def usage(d): return d.get("alphaCount") or 0
        ds.sort(key=usage, reverse=True)
        print(f"\n=== DATASETS ({len(ds)}), by alphaCount desc ===", flush=True)
        for d in ds:
            print(f"  {d.get('id'):16s} fields={d.get('fieldCount')} "
                  f"alphas={d.get('alphaCount')} cov={d.get('coverage')} | {d.get('name')}",
                  flush=True)

        # --- FIELDS for the TOP-USAGE datasets the generator does NOT mine ---
        MINED = {"fundamental6"}  # generator's value ratios already come from here
        targets = [d for d in ds if d.get("id") not in MINED][:22]
        print(f"\n=== SAMPLE FIELDS for top {len(targets)} datasets (MATRIX, cov>=0.5) ===",
              flush=True)
        for d in targets:
            did = d.get("id")
            flds = await _paginate(c, "/data-fields",
                                   {**eq, "type": "MATRIX", "dataset.id": did}, cap=60)
            flds = [f for f in flds if (f.get("coverage") or 0) >= 0.5]
            names = [f"{f.get('id')}" for f in flds[:36]]
            print(f"\n  # {did} ({d.get('name')}) — {len(flds)} MATRIX fields cov>=0.5:",
                  flush=True)
            print("    " + ", ".join(names), flush=True)
    finally:
        await client.aclose()
        if pool:
            await pool.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
