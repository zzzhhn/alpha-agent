"""Discovery: dump the BRAIN data-field vocabulary for the mining account.

The generator's economic ratios are hardcoded from CONFIRMED field ids — a wrong
id simulates as an "unknown variable" error. Before widening the generator into
new fundamental families (growth / quality / analyst / investment), this lists the
datasets the account can see and, per fundamental/analyst dataset, prints
`id | coverage | description` so ratios are built only from real, well-covered
fields. API-only (no simulations) — finishes in seconds.

Env: BRAIN_USERNAME/BRAIN_PASSWORD (preferred) or DATABASE_URL (+ BYOK_MASTER_KEY)
to decrypt the vault. Optional BRAIN_MINING_USER_ID.
"""
import asyncio
import os
import sys

# Datasets to always dump even if enumeration misses them (the known fundamentals
# + analyst the generator already draws on). Enumeration adds any others found.
_SEED_DATASETS = ("fundamental6", "fundamental2", "fundamental3", "analyst4")
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
        user_id: int | None = int(uid)
    else:
        row = await pool.fetchrow(
            "SELECT user_id FROM user_byok WHERE provider='worldquant_brain' "
            "ORDER BY encrypted_at DESC LIMIT 1"
        )
        user_id = row["user_id"] if row else None
    creds = await vault.load_brain_credentials(pool, user_id) if user_id else None
    return creds, pool


async def _probe(c, ds: str, extra: dict) -> tuple[int, int]:
    """First-page probe for one query variant. Returns (http_status, result_count)
    so we can SEE why a dataset comes back empty (403? 0 results at this delay?)."""
    try:
        r = await c.get(
            "/data-fields",
            params={**_REGION, "dataset.id": ds, "limit": 50, "offset": 0, **extra},
        )
        n = len(r.json().get("results", [])) if r.status_code == 200 else 0
        return r.status_code, n
    except Exception as e:  # noqa: BLE001
        print(f"  probe {ds} {extra}: EXC {type(e).__name__}", flush=True)
        return 0, 0


async def _dump_dataset(c, ds: str, *, cap: int = 200) -> None:
    """Dump fields for one dataset. First diagnose the empty case: probe a few
    query variants (type filter on/off, delay 0/1) and log status+count for each,
    then dump using the first variant that returns rows."""
    print(f"=== FIELDS {ds} ===", flush=True)
    variants = [
        {"type": "MATRIX"},
        {},                       # no type filter
        {"type": "MATRIX", "delay": 0},
        {"delay": 0},
    ]
    chosen = None
    for v in variants:
        status, n = await _probe(c, ds, v)
        print(f"  probe {v or '{}'}: status={status} rows={n}", flush=True)
        if n > 0 and chosen is None:
            chosen = v
    if chosen is None:
        print(f"  ({ds}: no variant returned rows)", flush=True)
        return

    offset = 0
    printed = 0
    while printed < cap:
        try:
            r = await c.get(
                "/data-fields",
                params={**_REGION, "dataset.id": ds, "limit": 50, "offset": offset,
                        **chosen},
            )
            if r.status_code != 200:
                break
            results = r.json().get("results", [])
        except Exception as e:  # noqa: BLE001 — best-effort per dataset
            print(f"  (fetch failed: {type(e).__name__})", flush=True)
            break
        if not results:
            break
        for f in results:
            desc = (f.get("description") or "").replace("\t", " ")[:90]
            print(f"F\t{ds}\t{f.get('id')}\t{f.get('coverage')}\t{desc}", flush=True)
            printed += 1
        offset += 50
    print(f"  ({printed} fields in {ds} via {chosen or 'MATRIX'})", flush=True)


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

        # 1) Enumerate datasets (best-effort) to discover families we don't know.
        datasets: list[str] = list(_SEED_DATASETS)
        try:
            r = await c.get("/data-sets", params=_REGION)
            if r.status_code == 200:
                print("=== DATASETS ===", flush=True)
                for d in r.json().get("results", []):
                    cat = d.get("category")
                    cat_name = cat.get("name") if isinstance(cat, dict) else cat
                    did = d.get("id")
                    print(f"DS\t{did}\t{d.get('fieldCount')}\t{cat_name}\t{d.get('name')}",
                          flush=True)
                    # widen the dump to fundamental/analyst/model families
                    hay = f"{did} {cat_name} {d.get('name')}".lower()
                    if any(k in hay for k in ("fundamental", "analyst", "estimate",
                                              "earnings", "model", "growth")):
                        datasets.append(did)
        except Exception as e:  # noqa: BLE001 — enumeration is optional
            print(f"(dataset enumeration failed: {type(e).__name__})", flush=True)

        # 2) Dump fields for each fundamental/analyst dataset (deduped, order-kept).
        for ds in dict.fromkeys(d for d in datasets if d):
            await _dump_dataset(c, ds)
    finally:
        await client.aclose()
        if pool:
            await pool.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
