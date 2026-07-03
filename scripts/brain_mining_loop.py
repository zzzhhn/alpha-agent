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
            # Single-user default: the account with BRAIN creds in the vault,
            # else the sole user. Set BRAIN_MINING_USER_ID for a multi-user setup.
            row = await pool.fetchrow(
                "SELECT user_id FROM user_byok WHERE provider='worldquant_brain' "
                "ORDER BY encrypted_at DESC LIMIT 1"
            )
            if row is None:
                row = await pool.fetchrow(
                    "SELECT id AS user_id FROM users ORDER BY id LIMIT 1"
                )
            if row is None:
                print(json.dumps({"ok": False, "error": "no user found; set BRAIN_MINING_USER_ID"}))
                return 1
            user_id = row["user_id"]

        # Credentials: env-provided GitHub secrets are PREFERRED — that path
        # needs no BYOK_MASTER_KEY here, which matters because the master key is
        # often a write-only Vercel "Sensitive" var you can't read back to copy.
        # Falls back to decrypting the vault (which does need the key).
        env_user = os.environ.get("BRAIN_USERNAME")
        env_pass = os.environ.get("BRAIN_PASSWORD")
        if env_user and env_pass:
            creds = (env_user, env_pass)
        else:
            creds = await vault.load_brain_credentials(pool, user_id)
        if creds is None:
            print(json.dumps({"ok": False, "error": "no BRAIN credentials: set BRAIN_USERNAME + BRAIN_PASSWORD secrets, or BYOK_MASTER_KEY to decrypt the vault"}))
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
