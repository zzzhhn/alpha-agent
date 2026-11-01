# Research validation quarantine

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

No replacement validator or profitable strategy is claimed by the recovery
release. This document records an open correctness task, not completed research.
