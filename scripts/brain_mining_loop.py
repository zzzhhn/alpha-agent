"""Phase E4 runner: one WorldQuant BRAIN mining round, for the GitHub Actions
job. Loads the target user's encrypted BRAIN credentials from the vault, opens a
Neon pool, runs one round, and prints a JSON summary.

Runs on GitHub Actions (not Vercel) because BRAIN simulations poll for minutes.
Env: DATABASE_URL, BYOK_MASTER_KEY, BRAIN_MINING_USER_ID, BRAIN_N_CANDIDATES?"""
import asyncio
import json
import os
import sys


async def _main() -> int:
    import asyncpg

    from alpha_agent.brain import vault
    from alpha_agent.brain.client import BrainClient
    from alpha_agent.brain.mining_loop import run_mining_round

    n = int(os.environ.get("BRAIN_N_CANDIDATES", "8"))
    uid_env = os.environ.get("BRAIN_MINING_USER_ID")

    pool = await asyncpg.create_pool(
        os.environ["DATABASE_URL"], min_size=1, max_size=2
    )
    try:
        if uid_env:
            user_id = int(uid_env)
        else:
            # Single-user default: the (only) account with BRAIN creds in the
            # vault. Set BRAIN_MINING_USER_ID to disambiguate a multi-user setup.
            row = await pool.fetchrow(
                "SELECT user_id FROM user_byok WHERE provider='worldquant_brain' "
                "ORDER BY encrypted_at DESC LIMIT 1"
            )
            if row is None:
                print(json.dumps({"ok": False, "error": "no BRAIN credentials in vault; connect an account in Settings"}))
                return 1
            user_id = row["user_id"]

        creds = await vault.load_brain_credentials(pool, user_id)
        if creds is None:
            print(json.dumps({"ok": False, "error": f"no BRAIN credentials for user {user_id}"}))
            return 1
        client = BrainClient(creds[0], creds[1])
        try:
            summary = await run_mining_round(client, pool, user_id, n_candidates=n)
        finally:
            await client.aclose()
        print(json.dumps({"ok": True, "user_id": user_id, **summary}))
        return 0
    finally:
        await pool.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
