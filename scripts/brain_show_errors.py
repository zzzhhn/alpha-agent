"""Diagnostic: print the most recent BRAIN mining results' details (esp. the
sim_error reasons) straight from the DB. Fast — no BRAIN calls. Used to see WHY
a mining round failed without waiting for another full simulate round.

Env: DATABASE_URL, BRAIN_MINING_USER_ID? (defaults to the sole BRAIN user)."""
import asyncio
import os


async def _main() -> None:
    import asyncpg

    pool = await asyncpg.create_pool(os.environ["DATABASE_URL"], min_size=1, max_size=2)
    try:
        uid_env = os.environ.get("BRAIN_MINING_USER_ID")
        if uid_env:
            user_id = int(uid_env)
        else:
            row = await pool.fetchrow(
                "SELECT user_id FROM user_byok WHERE provider='worldquant_brain' "
                "ORDER BY encrypted_at DESC LIMIT 1"
            )
            user_id = row["user_id"] if row else None
        if user_id is None:
            print("no BRAIN user found")
            return
        rows = await pool.fetch(
            "SELECT created_at, outcome, expression, detail, sharpe, fitness, "
            "turnover, self_correlation FROM brain_alphas "
            "WHERE user_id=$1 ORDER BY created_at DESC LIMIT 20",
            user_id,
        )
        print(f"=== last {len(rows)} brain_alphas for user {user_id} ===")

        def _f(v):
            return f"{v:.2f}" if isinstance(v, (int, float)) else "—"

        for r in rows:
            print(f"[{r['outcome']}] {r['expression'][:80]}")
            print(
                f"    Sharpe={_f(r['sharpe'])} Fitness={_f(r['fitness'])} "
                f"TO={_f(r['turnover'])} selfcorr={_f(r['self_correlation'])}"
            )
            if r["detail"]:
                print(f"    detail: {r['detail']}")
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(_main())
