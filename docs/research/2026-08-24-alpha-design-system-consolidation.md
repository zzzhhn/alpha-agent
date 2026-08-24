# Alpha Agent Design System Consolidation

Status: implementation milestone deployed to production

Date: 2026-08-24

Branch: `codex/alpha-design-system-consolidation`

## Objective

Consolidate Alpha Agent's desktop workstation into one production design
language. The same action, status, metric, navigation pattern, and recovery path
must look and behave consistently across routes. The deliverable is not only a
proposal: it includes canonical production components, a living `/reference`
route, an explicit migration ledger, route adoption, and browser acceptance.

## Product boundaries

- Desktop at 1440 x 900 and 1672 x 941 is the primary layout target.
- Mobile remains usable but is not allowed to distort desktop information
  density.
- Authentication may keep its centred, lower-density composition while sharing
  canonical foundations, controls, and feedback.
- No sample component may masquerade as live market or account data.
- Page-local deviations require a user need, owner, and removal condition.

## Implemented foundation

- Added `/reference` under the existing sidebar `参考 / REFERENCE` category.
- Added production specimens for foundations, controls, data display, feedback,
  overlays, charts, and operating patterns.
- Consolidated semantic tokens, focus treatment, type roles, spacing, radius,
  and 24, 28, and 32 px control heights.
- Added or hardened `TmButton`, `TmField`, `TmBadge`, `TmPagination`,
  `TmStatePane`, `TmTooltip`, `TmDialog`, `TmToggleGroup`, `SegmentedTabs`, and
  chart token adapters.
- Kept legacy button and tooltip imports as compatibility aliases to canonical
  production assets.

## Production migration completed so far

| Surface | Change | User-visible contract |
| --- | --- | --- |
| Topbar | locale and theme selectors use `TmToggleGroup` | 24 px geometry, visible selection, Arrow/Home/End keyboard behavior |
| BRAIN candidate audit | filter selector and refresh action use canonical controls | one filter grammar and stable loading button |
| Backtest form | all selects, numeric inputs, expression field, checkboxes, reset, advanced, and run actions use canonical controls | 32 px desktop geometry, one primary action, unchanged validation and parameter semantics |
| Backtest decision surfaces | rerun, save, pin, row icon actions, and daily download use canonical buttons | shared loading, danger, secondary, ghost, and icon-only behavior |
| Alerts | severity and relevance filters plus shared commands use canonical controls | radio-semantic filters, keyboard navigation, and fixed control density |
| BRAIN results | local pagination replaced by `TmPagination` | run-scoped pages, page-size reset, accessible navigation labels |
| Screener factor picker | local pagination replaced by `TmPagination` | filter state retained and empty pages reconcile safely |
| Evolution proposals | local pagination replaced by `TmPagination` | five-row bounded queue and single expanded proposal |
| Tooltips | two legacy components alias `TmTooltip` | shared portal, viewport clamp, Escape, and focus behavior |
| Alpha research input | hypothesis, validation parameters, examples, rerun, and optional analytics use canonical fields, buttons, disclosure, and dialog | one action hierarchy, 32 px control grammar, and focus-restoring example overlay |
| Settings | provider, credentials, watchlist, weights, destructive confirmation, and loading actions use canonical fields and buttons | consistent labels, truthful busy states, preserved credential privacy and validation |
| Paper workstation | recommendation, position, order, and attribution tables use `TmTable` | shared compact or standard density, selected rows, numeric alignment, and accessible captions |
| Backtest evidence states | equity, drawdown, and walk-forward loading, empty, and error surfaces use `TmStatePane` | stable pane geometry and one lifecycle grammar |
| Standard data tables | Picks, Paper, BRAIN, Backtest, Alerts, Screener, Evolution, Factor Lab, Factors, and Stock detail use `TmTable` | one density, caption, sorting, selected-row, numeric-alignment, and overflow contract |
| Charts | Backtest equity, drawdown, and walk-forward charts consume `chartTokens` | dark/light semantic palette shared with `/reference` |

## Verification completed

- TypeScript, focused lint, and the full production build pass for the current
  canonical control and route-migration batch.
- Visible Chrome checks passed for dark Chinese at 1672 x 941, light English at
  1440 x 900, and the narrow desktop boundary at 1024 px.
- `/reference` pagination changes real specimen rows and resets correctly after
  page-size changes.
- Toggle groups and tabs pass Arrow, Home, and End keyboard navigation.
- Tooltip focus and Escape behavior passed in the browser. `TmDialog` also
  passed focus entry, Escape close, focus trap, and trigger-focus restoration.
- Backtest and Paper workstations showed no horizontal overflow at their 1672
  px desktop target. `/reference` showed no overflow at 1440 or 1024 px.
- The browser console reported no errors in the accepted anonymous-route run.

`/alpha` and `/settings` redirect anonymous sessions to sign-in. Their static,
type, lint, and build gates pass, but authenticated production-path browser
acceptance remains a separate post-deployment gate.

## Production release

- Implementation merged through PR #27 to `main`.
- Vercel Git integration deployed the merged revision as frontend deployment
  `dpl_G2qCzqUd9oDWc7a7NbTosrF154gT` and assigned
  `https://alpha.bobbyzhong.com`.
- `https://alpha.bobbyzhong.com/reference` returns the new Design System route,
  and the frontend content version is `cebd3de7e4b4be25`.
- `GET /api/_health` returns JSON with `tunnel=ok` and `db=ok`.
- Production OpenAPI exposes 136 paths, including the health surface.
- Visible Chrome acceptance against the custom domain passed dark/light,
  zh/en, pagination, keyboard controls, 1440 px and 1024 px overflow checks,
  and reported no browser errors.

## Remaining migration

The current static baseline still contains 113 raw buttons across 51 production
files and 43 raw field elements across 17 production files. They must be classified before
replacement because selectable rows, icon actions, native file controls, and
primary mutations have different semantics. The next batches are:

1. Shared action surfaces: icon buttons, pin/save/retry actions, and repeated
   workbench command rows.
2. Forms: remaining Screener, Report, Picks, Signal, and authentication controls
   mapped to the canonical field shell and button states.
3. Feedback: route-local loading, empty, error, stale, and partial blocks mapped
   to stable `TmStatePane` compositions.
4. Data surfaces: table density, selected rows, sorting labels, expandable
   evidence, and native tooltip replacements.
5. Charts and overlays: remove hard-coded colors and verify text summaries,
   focus entry, Escape close, and focus restoration.

This deployment is a substantial system-wide migration milestone, not a claim
that every historical raw element has disappeared. The work remains open until
the residual inventory is either migrated or listed as a justified exception,
and the authenticated route set passes browser acceptance.
