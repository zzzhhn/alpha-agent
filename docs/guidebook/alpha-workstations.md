# Alpha Workstation Guidebook

## Factor Alpha

Write one falsifiable hypothesis, confirm universe, direction, bucket size, cost, neutralization, and benchmark, then use “Translate and backtest.” After translation, “Rerun current expression” keeps the expression and uses the latest visible parameters. Read the verdict strip before opening detailed evidence. The example library is a starting-point catalogue, not proof that an example remains valid.

## Backtest

Load a saved factor or enter an expression, confirm the compact parameters, and run once. The first decision order is verdict, equity path, validation gates, baseline comparison, diagnostic summaries, then recent runs. Daily holdings and operational detail are disabled by default to reduce payload size; enable “Return daily breakdown” under Advanced and rerun when those panes are needed. Dashes mean evidence is unknown, not zero.

## Screener

Select interpretable factors first, then define sector, market-cap, combination, and as-of parameters. The decision strip summarizes selection count, target count, eligible universe, and concentration before the results table. Missing or unclassified sectors remain visible in results but cannot be selected as a filter. Hover dotted quant terms for their Chinese or English definitions.

## Alerts

Start from “Needs action,” narrow by severity or related object, select the highest-ranked row, inspect evidence and exposure, then resolve or snooze. Research context is secondary to disposition. If the feed fails, retry inside the queue pane; the rest of the triage workspace remains usable.

## Evolution Monitor

Read the overall decision strip, inspect the three highest-risk signals, review the promotion funnel, then process pending proposals beside the visible change ledger. Pending proposals show five per page and only one expands at a time. “All signals” opens weight and calibration detail. Co-occurring events are evidence links, not causal claims.

## BRAIN Mining

Treat one manual or scheduled mining invocation as one run. Select a recent run before reviewing candidates; filters and pagination then stay inside that run instead of mixing adjacent batches. Set the cheap generation pool above the real simulation budget so the logic screen can rank alternatives without increasing BRAIN calls. Read the funnel as requested, generated, screened, simulated, and persisted. These counts may differ, and the screen status explains whether the optional LLM screen completed, was partial, failed and bypassed, or was not configured. Options mining distributes its pool across IV skew level, skew dynamics, term structure, IV momentum, variance risk premium, PCR dynamics, and breakeven-forward mechanisms before repeating one. Discovery never silently replays historical structures; exhaustion is a visible failed run rather than a costly robustness retest. “Reuse run” loads the selected configuration but creates a new child run, preserving the original evidence. A zero-candidate run is a failure and submits no BRAIN simulations. A failed run remains in the ledger with its last durable counts and error reason. Candidate verdicts separate performance quality from novelty, so a strong but self-correlated alpha is shown as high quality and redundant instead of generically suspicious. Historical rows created before the run ledger remain available through the compatibility view.

## Shared state language

- `—`: unavailable or not yet returned.
- Green: healthy, validated, or the single primary action.
- Amber: incomplete evidence or review required.
- Red: failed, blocked, or explicit counter-evidence.
- Loading and error states keep their pane geometry, so the page does not jump or erase unrelated context.
