"""Apply pending DB migrations against DATABASE_URL. Idempotent — already-applied
versions are skipped (tracked in schema_migrations). Backs the apply-migrations
GitHub Actions workflow so schema changes (e.g. V028 brain_alphas) can be applied
without the admin endpoint, using only the DATABASE_URL secret."""
import asyncio
import os

from alpha_agent.storage.migrations.runner import apply_migrations


def main() -> None:
    dsn = os.environ["DATABASE_URL"]
    applied = asyncio.run(apply_migrations(dsn))
    print("applied:", applied if applied else "(none pending — schema up to date)")


if __name__ == "__main__":
    main()
