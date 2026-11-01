# Safe cron recovery

Deploy the backend preflight endpoint before enabling scheduled work. Frontend
and backend are separate Vercel projects; both must finish deployment.

## Read-only smoke

Run the `cron-preflight` workflow manually on `main`. It uses the same GitHub
`CRON_SECRET` as ingestion, checks the deployed endpoint, and performs only a
bounded `pg_database_size` query. It does not ingest, prune, trade or invoke LLMs.
Manual failures stay failures. This workflow has no schedule.

`DB_STORAGE_BUDGET_MIB` defaults to 512; ingestion is paused at 80% of that budget.
This is an operating budget, not the provider quota. It measures the current
database's physical size, not all branches, transfer, compute or future writes.

On known infrastructure pauses, scheduled callers skip their business jobs and
write `PAUSED, no work executed` in the summary. A green wrapper is not evidence
of fresh prices or successful ingestion. Auth and application errors remain
failures. Unrelated workflows and direct API callers are not covered by this gate.

## Before re-enabling the three schedules

1. Verify production health, router loading, frontend and authenticated preflight.
2. Inspect provider usage, queue age and market-data freshness separately.
3. After a long outage, backfill a bounded price window for a small ticker slice
   first. The daily `5d` fetch cannot recover a month-long gap. This is a write
   canary, not the read-only smoke above. Never fabricate historical predictions.
4. Validate coverage and expected market date before publishing recommendations.
5. Check each runner's budget and one bounded execution, then enable
   `cron-shards`, `propose-job-runner` and `daily-factor-loop` individually.

Do not automatically delete history to satisfy the capacity check. Do not
increase pool sizes or budgets merely to make the gate green.
