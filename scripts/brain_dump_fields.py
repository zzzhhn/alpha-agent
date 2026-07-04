"""Discovery: dump the BRAIN data-field vocabulary for the mining account.

The generator's economic ratios are hardcoded from CONFIRMED field ids — a wrong
id simulates as an "unknown variable" error. Before widening the generator into
new fundamental families (growth / quality / analyst / investment), this lists the
datasets the account can see and dumps each fundamental/analyst dataset's fields
as `id | coverage | description`, so ratios are built only from real fields.

The /data-fields endpoint rate-limits hard (429); earlier empty dumps were 429,
not missing access. So this goes SLOWLY with backoff, and only at delay=1 (the sim
delay — fields available only at delay 0 can't be used in the delay-1 sims).

Env: BRAIN_USERNAME/BRAIN_PASSWORD (preferred) or DATABASE_URL (+ BYOK_MASTER_KEY)
to decrypt the vault. Optional BRAIN_MINING_USER_ID.
"""
import asyncio
import os
import sys

# High-value fundamental/analyst/model datasets to dump (skip news/social/option).
_DUMP_DATASETS = ("fundamental6", "analyst4", "model16", "model77", "model51", "pv13")
_REGION = {"instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000", "delay": 1}


async def _load_creds():
    """(username, password), pool — env creds preferred (no master key needed);
    else decrypt the vault. Returns (creds_or_None, pool_or_None)."""
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


async def _get(c, path: str, params: dict, *, retries: int = 6):
    """GET with 429 backoff — the data-fields endpoint rate-limits aggressively."""
    r = None
    for attempt in range(retries):
        r = await c.get(path, params=params)
        if r.status_code != 429:
            return r
        await asyncio.sleep(2.0 * (attempt + 1))  # 2,4,6,8,10,12s
    return r


async def _dump_dataset(c, ds: str, *, cap: int = 150) -> None:
    """Dump MATRIX fields for one dataset at the sim delay, paginated gently."""
    print(f"=== FIELDS {ds} ===", flush=True)
    offset = 0
    printed = 0
    while printed < cap:
        r = await _get(
            c, "/data-fields",
            {**_REGION, "type": "MATRIX", "dataset.id": ds, "limit": 50, "offset": offset},
        )
        if r is None or r.status_code != 200:
            print(f"  (status {getattr(r, 'status_code', '?')} at offset {offset})", flush=True)
            break
        results = r.json().get("results", [])
        if not results:
            break
        for f in results:
            desc = (f.get("description") or "").replace("\t", " ")[:90]
            fid = f.get("id")
            cov = f.get("coverage")
            print("F\t{}\t{}\t{}\t{}".format(ds, fid, cov, desc), flush=True)
            printed += 1
        offset += 50
        await asyncio.sleep(1.5)
    print(f"  ({printed} fields in {ds})", flush=True)
    await asyncio.sleep(1.5)


async def _main() -> int:
    from alpha_agent.brain.client import BrainClient

    creds, pool = await _load_creds()
    if not creds:
        print("no BRAIN credentials (set BRAIN_USERNAME/BRAIN_PASSWORD)", flush=True)
        return 1

    client = BrainClient(creds[0], creds[1])
    try:
        await client.authenticate()
        c = client._client

        # List datasets once (best-effort) for the family overview.
        try:
            r = await c.get("/data-sets", params=_REGION)
            if r.status_code == 200:
                print("=== DATASETS ===", flush=True)
                for d in r.json().get("results", []):
                    cat = d.get("category")
                    cat_name = cat.get("name") if isinstance(cat, dict) else cat
                    print("DS\t{}\t{}\t{}\t{}".format(
                        d.get("id"), d.get("fieldCount"), cat_name, d.get("name")),
                        flush=True)
        except Exception as e:  # noqa: BLE001 — enumeration is optional
            print(f"(dataset enumeration failed: {type(e).__name__})", flush=True)
        await asyncio.sleep(1.5)

        for ds in _DUMP_DATASETS:
            await _dump_dataset(c, ds)
    finally:
        await client.aclose()
        if pool:
            await pool.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
