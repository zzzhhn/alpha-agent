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

## Bounded manual recovery

The manual `cron-preflight` dispatch defaults to read-only `check`. Its optional
recovery job is never scheduled or executed by reusable-workflow callers.
It rechecks capacity immediately before one request, has no automatic retries,
and keeps the cron credential inside GitHub Actions.

```sh
gh workflow run cron-preflight.yml --ref main \
  -f operation=daily_prices -f limit=5 -f offset=0
```

Prices default to a five-trading-day window and a maximum of 75 tickers per call. Start
with five; verify actual dates and capacity before increasing the slice. A
positive `updated` count includes existing-row upserts and is not a freshness
check. Missing feeds are explicitly `PARTIAL`; HTTP/database errors or zero
writes fail the manual action. Review both the response and actual DB coverage.
For a verified longer outage, explicitly pass `-f period=1mo` or `3mo`; do not
expand the window merely because the valid-row counter is small.

After the canary, `operation=ensure_research_prices` checks current-session
coverage of the exact planned Top-240 plus watchlist, and requires the SPY
close for that same session. It skips provider calls if ready. Otherwise it
walks the bounded price universe (at most 600 symbols, 75 per request, five-day
window), rechecks storage before each write, then reads actual-date coverage
again. This action does not compute IC, generate signals, publish, trade or
call an LLM. Watchlists, research symbols and SPY are included in the price
universe even when absent from old slow-signal rows. Unfinished current-session
candles are not stored as settled daily closes.

The full scheduled/manual `fast_intraday` workflow now depends on this price
stage, rather than assuming the separate 22:00 price cron finished before the
23:00 research cron. Insufficient fresh prices pause scheduled full research
with a visible warning and `ready=false`; unexpected auth/code errors still
fail normally. Final publication health gates are unchanged. A green paused
workflow is not a new recommendation. Manual recovery still fails if not ready.
Per-ticker provider failures remain in the receipt but do not override a passing
actual-coverage gate for the required universe. HTTP/auth/invalid-response
errors still fail. Each stage retains the starting UTC research day and leaves
a full request budget before midnight; an expired day pauses publication rather
than mixing ranking scopes. Scheduled L2 now follows successful publication in
the same workflow, not an independent 23:45 timer.

Other manual actions are `fast_intraday` (at most 40 plus watchlist additions),
`publish_recommendation`, `run_propose_jobs`, and `daily_factor_loop`. Inspect
queues before invoking a runner. They use the production handler's time budget.
Do not dispatch multiple recovery jobs concurrently.

Full signal refreshes and publication share the same prior-UTC-day ranking,
with deterministic ticker tie-breaking. Complete the six 40-name shards within
one UTC day; a recovery crossing midnight must recompute/revalidate the scope.
Publication checks the planned Top-240 plus watchlist, includes missing inputs
in the coverage denominator, and requires eligible signals computed after the
market session close. New prices cannot rehabilitate old signals. Partial runs
remain forensic records, not new canonical recommendations.

## Failure circuit breaker

`cron-circuit-breaker` watches only the three named workflows on `main`. After
an unexpected scheduled failure or timeout, it disables that specific workflow
and verifies the disabled state. The first failure remains visible; later
scheduled attempts stop. It does not change email preferences, erase failure
history, automatically retry, or automatically re-enable anything. Known quota
pauses still skip work through preflight rather than tripping the breaker.

The manual guard dispatch defaults to dry-run. An already-paused target is a
successful no-op; GitHub rejects an unconditional second disable with 403.
After a workflow's recovery gates pass, an explicit active-to-paused manual
dispatch can verify the write permission without manufacturing a failed business
run. Read back the state, then explicitly restore the workflow.
