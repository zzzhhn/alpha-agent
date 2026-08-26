# Alpha Agent Design System Consolidation

Status: phase 1 deployed; phase 2 implementation and browser acceptance complete

Date: 2026-08-24

Branches: `codex/alpha-design-system-consolidation`, `codex/alpha-design-system-consolidation-phase2`

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

## Phase 2 closure

The residual inventory was classified by interaction role and migrated across
authentication, shared shell, Alpha, BRAIN, Backtest, Alerts, Report, Screener,
Picks, Paper, Signal, Evolution, Factor Lab, Factors, Data, Settings, Stock, and
error or recovery routes.

New canonical assets:

- `TmRowButton` for full-row ledger and evidence actions without flattening
  them into ordinary command-button hierarchy.
- `TmRange` for labelled numeric sliders with a visible value and native
  keyboard semantics.
- `TmSelectMenu` for metadata-bearing rich options, with portal placement,
  disabled-option skipping, listbox keyboard behavior, and focus restoration.
- `TmDrawer` plus shared `useTmModalFocus` for focus entry, trap, Escape,
  scroll lock, overlay close, and trigger restoration.
- CSS and Canvas chart adapters that resolve all ordinary production series
  from semantic chart tokens.

`npm run audit:design-system` is now an executable release gate. The accepted
inventory is zero unexplained native controls, zero unexplained standard native
tables, two canonical-internal control files, one semantic heatmap matrix, and
a no-growth budget of 35 native truncation or compatibility titles.

## Phase 2 verification

- `tsc --noEmit`, `git diff --check`, the AST design-system audit, and the full
  Next.js production build pass.
- Dark Chinese and light English `/reference` checks passed at 1672 × 941 and
  1440 × 900. The 1024 px narrow-desktop boundary has no horizontal overflow.
- `TmSelectMenu` passed Arrow, Home, End, Enter, Space, Escape, disabled-option
  skipping, and trigger-focus restoration checks.
- `TmDialog` and `TmDrawer` passed focus entry, focus containment, Escape close,
  and trigger-focus restoration.
- `/reference`, `/brain`, `/paper`, `/screener`, and `/factors` rendered at
  1672 × 941 without horizontal overflow. Production screenshots were visually
  inspected rather than treating the reference gallery as sufficient proof.
- Anonymous local runs reported only the expected Auth.js configuration and
  unauthorized API noise because production credentials are deliberately not
  copied into the local browser environment. Authenticated custom-domain
  acceptance remains part of the post-merge production gate.

## Recorded exceptions and follow-up

- `SegmentedTabs` keeps its native button internals because they implement the
  canonical ARIA tab contract.
- Toast infrastructure keeps its private native controls; route code cannot use
  them as a page-local control family.
- `TmMonthlyReturnsHeatmap` keeps a native table for its two-dimensional sticky
  matrix semantics and data-driven cell ramp.
- The 35 native `title` attributes are bounded compatibility or truncation
  hints. New explanatory content must use `TmTooltip`; the audit rejects count
  growth.

Phase 2 is released by merging the reviewed branch into `main` and allowing the
existing Vercel Git integration to build the configured `frontend` root. A push
alone is not release evidence; the custom domain, frontend version endpoint,
backend health content type, OpenAPI path set, and representative production
routes must be checked after deployment.

## 2026-08-25 reference acceptance corrections

- Split interaction accent from positive outcome colors in both themes and
  exposed the already-used `--tm-accent-soft` token in the living palette.
- Raised canonical label, caption, control, table, tooltip, and state copy to a
  12 px minimum rather than enlarging only the gallery specimen.
- Normalized native select geometry and chevrons in `TmField` and
  `TmPagination`, including Safari-safe vertical centering and page-size width.
- Aligned loading and disabled button specimens at their control edge, added
  the missing left tooltip placement, and kept partial recovery copy on one
  desktop line while allowing narrow layouts to wrap.
- Centered icon-button content through the primitive, expanded the dialog
  specimen to 1120 × 360 px, and added the 720 px drawer width to the canonical
  scale.

Acceptance remains light and dark, Chinese and English, at 1672 × 941 plus the
1024 px narrow-desktop overflow boundary. Dialog, drawer, select, pagination,
and tooltip behavior are browser-visible gates, not inferred from build output.

## 2026-08-26 full asset inventory correction

The previous reference covered canonical primitives but did not prove full
platform coverage. The correction adds dedicated Icon and Visualization tabs,
renders all 49 imported Lucide icons plus 12 bounded text-glyph exceptions,
extracts the stock-detail radar into the shared `TmRadarChart`, and records all
25 detected route/component visualization assets together with graph-like
micro-primitives. Route-reachable, live-specimen, and source-only states are
distinct, so unused legacy charts no longer masquerade as route coverage.
All reference taxonomy headings now use Chinese and English product labels.
Legacy dot-delimited pane titles use a central localized compatibility map.

The visible typography floor is now enforced across TSX chart settings,
Tailwind arbitrary sizes, and CSS at 12 px. `--tm-bg-3`, `--tm-rule`, and
`--tm-rule-2` were separated perceptually in both themes. The design-system
audit now blocks missing icons, unregistered visualizations, under-floor type,
and raw reference taxonomy headings in addition to its existing control,
table, and native-title gates.
