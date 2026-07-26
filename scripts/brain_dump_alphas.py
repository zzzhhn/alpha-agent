"""Dump ALL of the user's BRAIN alphas (platform-side mined history) as JSONL.

The authoritative record of every simulated alpha — expression, settings, and
in-sample metrics — lives on BRAIN itself, so this needs ONLY the BRAIN_USERNAME
/ BRAIN_PASSWORD env creds: no DATABASE_URL, which is the point (built while the
Neon quota outage had the DB-side history unreachable, 2026-07-26).

Writes one JSON object per line to brain_alphas_dump.jsonl for artifact upload.
Read-only; a paginated GET /users/self/alphas is a cheap, non-lazy endpoint.
"""
import asyncio
import json
import os


async def _main() -> int:
    from alpha_agent.brain.client import BrainClient

    user = os.environ.get("BRAIN_USERNAME")
    pw = os.environ.get("BRAIN_PASSWORD")
    if not (user and pw):
        print("BRAIN_USERNAME/BRAIN_PASSWORD required", flush=True)
        return 1

    client = BrainClient(user, pw)
    total = 0
    try:
        await client.authenticate()
        c = client._client
        with open("brain_alphas_dump.jsonl", "w", encoding="utf-8") as out:
            offset = 0
            while True:
                r = await c.get(
                    "/users/self/alphas",
                    params={"limit": 100, "offset": offset,
                            "order": "-dateCreated"},
                )
                if r.status_code != 200:
                    print(f"page offset={offset} -> HTTP {r.status_code}; stop",
                          flush=True)
                    break
                results = (r.json() or {}).get("results", [])
                if not results:
                    break
                for a in results:
                    out.write(json.dumps(a) + "\n")
                total += len(results)
                print(f"page offset={offset}: +{len(results)} (total {total})",
                      flush=True)
                offset += 100
                await asyncio.sleep(1.0)  # polite pacing; ~8-10 pages expected
    finally:
        await client.aclose()
    print(f"DONE: {total} alphas dumped", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
