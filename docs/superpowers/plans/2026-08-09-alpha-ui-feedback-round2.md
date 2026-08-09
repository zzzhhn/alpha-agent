# Alpha workstation UI feedback round two

## Calibrated outcome

Implement the four user-reported gaps without inventing new data or increasing the default backend payload:

1. Alpha: align examples and hidden analytics with the workbench visual system; permit parameter-only reruns of the current translated expression.
2. Backtest: replace the five KPI gate rows with five robustness questions; restore the existing opt-in daily-breakdown API path; explain empty holdings and operations; remove fixed-width dead space.
3. Screener: use the decision-first desktop baseline because no canonical Screener image is present; remove invalid sector filters; localize Chinese chrome and define technical terms.
4. Evolution: bound pending and ledger density; add plain-language definitions for quant abbreviations.

No database migration, permission change, security change, or new permanent audit record is required. Runtime behavior changes are limited to an existing request parameter and an existing backtest endpoint.

## Compatibility and ownership

- Design source: `docs/design-system/ALPHA-WORKSTATION-MASTER.md`.
- Reference images: Factor Alpha, Backtest, and Evolution native images in the redesign proposal. No Screener image was found in the repository or continuation packs.
- API compatibility: `include_breakdown` is already optional in `FactorBacktestRequest`; default remains false for performance.
- Data correctness: missing evidence is labelled missing, never passed. `Unknown` sectors are excluded only from filter choices, not silently removed from results.

## Principles re-check

1. Status stays visible in headers and local panes.
2. Each screen has one filled primary action.
3. Parameter-only rerun preserves the translated expression and uses current visible parameters.
4. Heavy data is opt-in and its bandwidth cost is explicit.
5. Empty states explain cause, impact, and recovery.
6. Validation distinguishes missing, warning, failure, and pass.
7. Desktop grids fill their containers and avoid decorative dead space.
8. Chinese UI translates interface language while standard abbreviations retain definitions.
9. Long queues paginate and expansion is bounded.
10. Existing API semantics outrank visual resemblance.

## Verification

- TypeScript type check and focused unit tests.
- Production build.
- 1672 × 941 Chinese dark-mode browser captures for `/alpha`, `/backtest`, `/screener`, and `/evolution`.
- Confirm no horizontal overflow, page-level runtime error, hidden recovery path, or unbounded proposal list.
