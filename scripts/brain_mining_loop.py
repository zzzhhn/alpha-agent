"""Phase E4 runner: one WorldQuant BRAIN mining round, for the GitHub Actions
job. Loads the target user's encrypted BRAIN credentials from the vault, opens a
Neon pool, runs one round, and prints a JSON summary.

Runs on GitHub Actions (not Vercel) because BRAIN simulations poll for minutes.
Env: DATABASE_URL, BYOK_MASTER_KEY, BRAIN_MINING_USER_ID, BRAIN_N_CANDIDATES,
BRAIN_GENERATION_TARGET, BRAIN_RUN_ID (manual dispatch), BRAIN_FAMILY_FOCUS,
BRAIN_SEED."""
import asyncio
import json
import os
import sys


async def _main() -> int:
    import asyncpg

    from alpha_agent.brain import vault
    from alpha_agent.brain.client import BrainClient
    from alpha_agent.brain.mining_loop import run_mining_round

    try:
        n = max(1, min(int(os.environ.get("BRAIN_N_CANDIDATES", "8")), 30))
    except (TypeError, ValueError):
        n = 8
    try:
        generation_target = max(
            n,
            min(int(os.environ.get("BRAIN_GENERATION_TARGET", str(n * 2))), 60),
        )
    except (TypeError, ValueError):
        generation_target = min(n * 2, 60)
    family_focus = os.environ.get("BRAIN_FAMILY_FOCUS") or None
    try:
        seed = int(os.environ.get("BRAIN_SEED", "1234"))
    except (TypeError, ValueError):
        seed = 1234
    run_id_env = os.environ.get("BRAIN_RUN_ID") or ""
    github_run_id = os.environ.get("GITHUB_RUN_ID") or None
    uid_env = os.environ.get("BRAIN_MINING_USER_ID")

    pool = await asyncpg.create_pool(
        os.environ["DATABASE_URL"], min_size=1, max_size=2
    )
    try:
        run_id: int | None = None
        if run_id_env:
            try:
                run_id = int(run_id_env)
            except (TypeError, ValueError):
                print(json.dumps({"ok": False, "error": "invalid BRAIN_RUN_ID"}))
                return 1
            run_row = await pool.fetchrow(
                "SELECT user_id FROM brain_runs WHERE id=$1", run_id
            )
            if run_row is None:
                print(json.dumps({"ok": False, "error": "BRAIN run not found"}))
                return 1
            user_id = int(run_row["user_id"])
            if uid_env:
                try:
                    uid_check = int(uid_env)
                except (TypeError, ValueError):
                    print(json.dumps({"ok": False, "error": "invalid BRAIN_MINING_USER_ID"}))
                    return 1
                if uid_check != user_id:
                    print(json.dumps({"ok": False, "error": "run/user mismatch"}))
                    return 1
        elif uid_env:
            try:
                user_id = int(uid_env)
            except (TypeError, ValueError):
                print(json.dumps({"ok": False, "error": "invalid BRAIN_MINING_USER_ID"}))
                return 1
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

        if run_id is None:
            from alpha_agent.brain import store

            run_row = await store.create_brain_run(
                pool,
                user_id=user_id,
                source="schedule",
                requested_n=n,
                generation_target_n=generation_target,
                family_focus=family_focus,
                seed=seed,
                github_run_id=github_run_id,
            )
            run_id = int(run_row["id"])
        else:
            from alpha_agent.brain import store

            if github_run_id:
                await store.update_brain_run(
                    pool, run_id, github_run_id=github_run_id
                )
            await store.mark_brain_run_running(pool, run_id)

        # Credentials: env-provided GitHub secrets are PREFERRED — that path
        # needs no BYOK_MASTER_KEY here, which matters because the master key is
        # often a write-only Vercel "Sensitive" var you can't read back to copy.
        # Falls back to decrypting the vault (which does need the key).
        env_user = os.environ.get("BRAIN_USERNAME")
        env_pass = os.environ.get("BRAIN_PASSWORD")
        if env_user and env_pass:
            creds = (env_user, env_pass)
        else:
            try:
                creds = await vault.load_brain_credentials(pool, user_id)
            except Exception as exc:  # noqa: BLE001 — record lifecycle failure
                await store.fail_brain_run(
                    pool,
                    run_id,
                    error_detail=f"credential load failed: {type(exc).__name__}",
                )
                print(json.dumps({"ok": False, "error": "credential load failed"}))
                return 1
        if creds is None:
            await store.fail_brain_run(
                pool, run_id, error_detail="no BRAIN credentials configured"
            )
            print(json.dumps({"ok": False, "error": "no BRAIN credentials: set BRAIN_USERNAME + BRAIN_PASSWORD secrets, or BYOK_MASTER_KEY to decrypt the vault"}))
            return 1
        # Optional LLM financial-logic pre-screen. If MINING_LLM_KEY is set,
        # build a client to score candidates' economic sense before the (slow)
        # BRAIN sims; otherwise the screen is a no-op.
        #
        # Provider detection matters: a Kimi-for-coding key (sk-kimi-*) MUST go
        # through KimiClient, which sets the User-Agent the coding endpoint gates
        # on — LiteLLM's providers drop it and get a 403. _build_byok_client
        # handles that exactly (same path as the app's BYOK). The key is only
        # passed to the client constructor and is never printed/logged.
        logic_llm = None
        llm_key = os.environ.get("MINING_LLM_KEY")
        if llm_key:
            try:
                from alpha_agent.api.byok import _build_byok_client

                provider = os.environ.get("MINING_LLM_PROVIDER")
                if not provider:
                    provider = "kimi" if llm_key.startswith("sk-kimi-") else "openai"
                logic_llm = _build_byok_client(
                    provider=provider,
                    api_key=llm_key,
                    api_base=os.environ.get("MINING_LLM_BASE") or None,
                    model=os.environ.get("MINING_LLM_MODEL") or None,
                )
                print(f"[logic] pre-screen LLM ready (provider={provider})", flush=True)
            except Exception as e:  # noqa: BLE001 — screen stays optional
                # Print only the exception TYPE, never the message — a provider
                # error could echo the request incl. the key.
                print(f"[logic] LLM init failed ({type(e).__name__}), screening off", flush=True)

        client = BrainClient(creds[0], creds[1])
        try:
            summary = await run_mining_round(
                client,
                pool,
                user_id,
                n_candidates=n,
                generation_target_n=generation_target,
                logic_llm=logic_llm,
                run_id=run_id,
                rng_seed=seed,
                family_focus=family_focus,
            )
        finally:
            await client.aclose()
        print(json.dumps({"ok": True, "user_id": user_id, "run_id": run_id, **summary}))
        return 0
    finally:
        await pool.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
