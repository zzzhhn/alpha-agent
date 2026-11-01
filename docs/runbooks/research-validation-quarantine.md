# Research validation quarantine

Latest follow-up: [current-data refresh, LLM identity and PARA quarantine](research-refresh-and-security-identity.md).
The April 30 dataset and missing `SYSTEM_USER_ID` observations below are historical
incident receipts, not the final repaired state.

## Discovery and scope

The 2026-11-01 production recovery canary for `daily_factor_loop` returned HTTP
200 in 106 seconds, evaluated five candidates and proposed zero. Its diagnostic
payload contained repeated `fold_kernel_exception` errors for missing `sector`,
including the baseline expression. Zero reported Sharpe is not reliable evidence
of a bad factor here: the evaluation inputs were invalid.
The manual recovery checker now also rejects nested `fold_kernel_exception`
diagnostics, not only top-level HTTP/arm errors. The original green wrapper is
retained as historical evidence, not re-labelled a healthy business execution.

The actual call chain is `cron_daily_factor_loop -> _run_ga_work ->
_evaluate_and_record -> evaluate_factor_candidate`. The LLM factor proposer
shares `_evaluate_and_record`. Code inspection confirmed:

- GA fitness loads the richer real panel through `factor_backtest._load_panel`.
- `evolution/factor_validation.py` independently loads only database close
  history, then builds a different panel: randomized open/high/low auxiliaries,
  fixed volume, placeholder dates and a random benchmark. It omits sector and
  fundamentals. Missing fundamentals become NaN operands; fold exceptions are
  appended as zero metrics instead of invalidating the evaluation.
- `evolution/validation.py`, called by the methodology proposer, has the same
  synthetic-panel construction. Neither validator is a test-only path.

This finding concerns the local evolution/proposal validators. It does not mean
that the BRAIN official simulator, the main historical factor-backtest panel,
or the recommendation signal/ledger pipelines use this synthetic construction.

## Current operational boundary

- Keep `daily-factor-loop` and `propose-job-runner` disabled until the criteria
  below are met. Empty-queue runner success is not proof that factor evaluation
  works.
- Remove the weekly methodology-proposer schedule from `cron-shards`. A manual
  selection explains the quarantine and performs no proposal work.
- Continue verified market-data and recommendation jobs. Do not automatically
  approve proposals, replace the live strategy, delete prior evidence, or rerun
  orphaned jobs to conceal this incident.
- The legacy API implementations still exist. Do not manually invoke the
  quarantined research paths as investment evidence while remediation is open.

## Next implementation order

1. **P0: data integrity and failure semantics.** Replace synthetic auxiliaries
   with a shared real-data panel; reject unavailable operands before expensive
   evaluation. Preserve real dates, symbols, sector metadata and point-in-time
   fundamentals. Missing data and kernel exceptions must be `invalid_evaluation`,
   not a numeric zero or a successful research result. A bad baseline cannot
   qualify a candidate.
2. **P0: chronological validation.** Review the existing train/test stacking.
   Compute time-series operators on the original chronological panel, apply
   proper purge/embargo and evaluate the actual held-out dates. Do not splice
   unrelated date blocks into a continuous return series.
3. **P1: bounded shared loading.** Load and align the panel once per run, not
   once for each candidate and baseline. Keep ticker/date limits, compute
   budgets and explicit field-coverage diagnostics. Do not expand database
   storage or subscribe to data services merely to make this check green.
4. **P1: independent verification.** Compare a small known expression against
   the same real panel in the main backtest kernel. Verify missing-field and
   invalid-baseline rejection, then one bounded production run. Restore the two
   workflows individually only after their full business path is valid.
5. **P2: investment usefulness.** Maintain daily marked paper-account values,
   costs and benchmark comparisons against immutable prospective snapshots.
   Separate historical descriptive hit rates from out-of-sample, executable
   returns; neither a healthy pipeline nor an accepted proposal proves profit.

## Remediation, 2026-11-01

The replacement `research_panel.py` now shares the main backtest's real OHLCV,
SPY, sector metadata, membership and filing-date fundamentals. It bounds the
research window to 504 sessions and loads once per run. Current bundled data
ends **2026-04-30**, explicitly historical, not current-market verification.
Missing PIT/membership data is a hard invalid evaluation, never a synthetic fill.

GA searches only the chronological development prefix. Three later contiguous
blocks retain their actual dates, with five-session gaps. The kernel is run on
the intact chronological panel; no train/test row stacking. Missing operands,
degenerate folds and kernel failures cannot become numeric-zero evidence. The
baseline must be valid before candidates can be admitted. Costs are 10 bps per
side plus 100 annual bps short borrow assumptions, not measured broker quotes.
The historical holdout is reused between research runs; it is not an independent
live forward test or proof of profitability. Sector classifications are snapshots
and the main kernel's cross-sectional membership limitations remain relevant.

The methodology adapter no longer pretends rating/IC knobs affect the factor
kernel and no longer mutates the live config cache. Its weekly schedule remains
quarantined, outside the requested two-runner restoration.

Recovery gates: manual `research_validation` (read-only known-expression and
baseline canary), then the real daily loop, then the propose runner. Workflow
success now checks the response's business `ok`, not just HTTP 200. Restore each
only after its deployed-path checks. The circuit breaker remains enabled.

Production receipts after PR #51: read-only validation run `41294821882`
passed in 6.36 seconds with the actual baseline and a known expression, zero
rejections/writes. Daily-loop run `41294880012` passed in 17.93 seconds, five
candidates evaluated, three valid/pending and two explicitly invalid due to
degenerate signal coverage. No automatic approval. The LLM arm correctly
skipped because no `SYSTEM_USER_ID` is configured. Queue drain `41294944903`
passed with no queued jobs; this proves runner availability, not a new LLM call.
Both requested workflows were restored sequentially following those checks.
One earlier manual probe (`41294707244`) was dispatched before the production
switch completed and returned 404; it was not a recurring schedule failure.

Reference: [QuantConnect research guide](https://www.quantconnect.com/docs/v2/writing-algorithms/key-concepts/research-guide)
for temporal separation, point-in-time inputs and survivorship limitations.
