# Alpha Workstation Guidebook

## Design System Reference

Open `参考 / REFERENCE` and select `设计系统 / Design System` to inspect the
same tokens, controls, data displays, feedback states, overlays, chart palette,
and operating patterns used by production routes. Examples are labelled sample
content and do not represent live market or account data. New route-specific
controls should first be represented here or documented as an explicit native
exception in the asset catalog.

The reference also demonstrates the rich-option selector, numeric range,
dialog, and contextual drawer. Arrow, Home, and End move listbox selection;
Enter or Space confirms; Escape closes overlays and restores focus to the
trigger. These are the same interaction contracts used by production routes.
Accent green marks interaction and selection, while positive green marks a
validated or favorable outcome. The tooltip specimen covers all four portal
placements. Compact labels, captions, controls, and data share a 12 px minimum
so dense desktop layouts remain readable.

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

## Today Recommendations

Read the snapshot and policy state before interpreting any score. “1-day direction agreement” is a descriptive next-trading-day check for one ticker, while “5-day calibrated confidence” is the tactical policy's separate calibrated output. Use the fixed 5, 20, and 60 trading-day `BASKET.EDGE` cells as the medium-horizon ranking evidence: inspect long sleeve, short sleeve, long-short spread, rank-IC, and usable-date count together rather than selecting the best-looking horizon. The secondary 1-day Top/Bottom basket check reports long, short, market, costs, turnover, and SPY separately. A long-short spread is not automatically market-beta neutral.

## BRAIN Mining

Treat one manual or scheduled mining invocation as one run. Select a recent run before reviewing candidates; filters and pagination then stay inside that run instead of mixing adjacent batches. Set the cheap generation pool above the real simulation budget so the evidence screen can compare alternatives without increasing BRAIN calls. The simulation budget is a ceiling, not a quota: a completed run may intentionally use fewer slots when the remaining candidates lack official field coverage, outcome alignment, historical support, or behavioral novelty. Read the funnel as requested, generated, screened, simulated, and persisted; the run detail reports the retained evidence and explains unused slots. Use `Simulation Results` for candidates that reached official BRAIN simulation, and `Candidate Audit` for the full generated pool. The audit ledger is written before screening and shows each expression, settings, mechanism, evidence score, field coverage, LLM technical state, and exact selection or withholding reason. A timeout or provider error means the LLM screen failed technically; it does not mean the alpha failed a BRAIN backtest. Older runs may retain aggregate counts without per-candidate rows, in which case the interface explicitly states that the missing historical expressions cannot be reconstructed. Options mining separates IV skew, skew dynamics, term structure, IV momentum, variance risk premium, PCR dynamics, breakeven-forward, and anchor-residual mechanisms. PCR-gated call-minus-put variants share one behavioral cluster even when tenor or syntax differs. Expand a candidate to inspect its research evidence: paper hypothesis, predicted outcome, official datasets and coverage, semantic match, target alignment, exact settings context, falsification rule, and validated cheap-proxy estimates. `mapped=100%` means the field IDs were found, not that a paper's construction was faithfully reproduced. Call/put or short/long legs should share official tenor or moneyness; ordinary put-call open interest is not buyer-initiated opening flow. The proxy is deliberately small and may remain inactive when history, chronological holdout, support context, or drift evidence is insufficient. Its diversification value is derived from adjusted self-correlation, not a claim of measured portfolio alpha. Discovery never silently replays historical structures; exhaustion is a visible failed run rather than a costly robustness retest. “Reuse run” loads the selected configuration but creates a new child run, preserving the original evidence. A zero-generated-candidate run is a failure and submits no BRAIN simulations. A generated run with zero candidates clearing the evidence floor is a completed screen with unused budget, not a transport failure. A failed run remains in the ledger with its last durable counts and error reason. Candidate verdicts separate performance quality from novelty, so a strong but self-correlated alpha is shown as high quality and redundant instead of generically suspicious. Historical rows created before the run ledger remain available through the compatibility view.

## Shared state language

- `—`: unavailable or not yet returned.
- Green: healthy, validated, or the single primary action.
- Amber: incomplete evidence or review required.
- Red: failed, blocked, or explicit counter-evidence.
- Loading and error states keep their pane geometry, so the page does not jump or erase unrelated context.
