# Alpha Workstation Design System Asset Catalog

Status: implementation source of truth for reusable frontend assets

Applies to: every Alpha Agent frontend route, including dashboard workbenches,
reference pages, authentication flows, overlays, charts, loading states, and
responsive navigation.

Living reference route: `/reference`, under the sidebar `REFERENCE / 参考` group.

## 1. Product and design job

Alpha Agent is a desktop-first research workstation. The design system exists
to make the same action, status, metric, and navigation pattern look and behave
the same everywhere. Users should spend attention on evidence and decisions,
not on relearning controls between tabs.

Success means:

1. Production pages consume canonical primitives rather than copying local CSS.
2. `/reference` renders those exact primitives in every supported state.
3. Dark and light themes, Chinese and English, keyboard navigation, and stable
   async geometry work without page-specific exceptions.
4. A repository scan can identify any remaining raw or legacy control as an
   explicit migration item.

Anti-goal: a decorative component gallery that is disconnected from production
components, or a visual rewrite that hides missing data behind populated mocks.

## 2. Verified frontend breakdown

The 2026-08-24 inventory covered all files under `frontend/src`.

| Surface | Verified current state | Canonical destination |
| --- | --- | --- |
| Tokens | Legacy tokens and `--tm-*` coexist | `--tm-*` semantic tokens |
| Buttons | Production actions and rich rows use the canonical TM family | `TmButton`, `TmIconButton`, `TmLinkButton`, `TmDisclosureButton`, `TmRowButton` |
| Fields | Production forms use the canonical TM field family | `TmInput`, `TmNumberInput`, `TmSelect`, `TmSelectMenu`, `TmTextarea`, `TmCheckbox`, `TmRange` |
| Panes/cards | `TmPane`, legacy `Card`, and glass-card utilities | `TmPane` |
| Type scale | 20 arbitrary pixel sizes | named roles in section 4 |
| Heights | 27 arbitrary fixed heights | 24, 28, 32, 36, 44 px scale |
| Radius | 247 rounded-class matches | 0 px default, 2 px exception |
| Tables | Standard tables plus one native matrix heatmap | `TmTable`; documented matrix exception |
| Pagination | multiple incompatible local implementations | `TmPagination` |
| Status | pills, badges, text colors, and page-local alerts | `TmBadge`, `TmStatePane` |
| Tooltips | two components plus native `title` attributes | one accessible tooltip contract |
| Overlays | dialogs and drawers share one modal focus contract | `TmDialog`, `TmDrawer`, and `useTmModalFocus` |
| Charts | SVG and canvas charts consume semantic adapters | `chartTokens`, `TM_CHART_SERIES_CSS`, and resolved canvas palette |

These counts are a migration baseline, not a target to preserve. A raw native
element is allowed only when the canonical primitive cannot express required
semantics and the exception is recorded here.

## 3. Foundations

### 3.1 Color

Only semantic `--tm-*` tokens are valid inside production workstation assets.

| Role | Token | Meaning |
| --- | --- | --- |
| floor | `--tm-bg` | page and pane floor |
| raised | `--tm-bg-2` | header, control, selected neutral surface |
| hover | `--tm-bg-3` | hover or tertiary surface |
| primary text | `--tm-fg` | evidence and decision text |
| secondary text | `--tm-fg-2` | explanation and metadata |
| muted text | `--tm-muted` | labels with AA-readable contrast |
| rule | `--tm-rule` | default hairline |
| strong rule | `--tm-rule-2` | selected or emphasized boundary |
| primary/positive | `--tm-accent`, `--tm-pos` | primary action, valid, healthy |
| warning | `--tm-warn` | incomplete, stale, review required |
| negative | `--tm-neg` | failed, blocked, destructive |
| informational | `--tm-info` | neutral system information |

Color is never the only state carrier. Every semantic color is paired with a
text label, icon, or explicit status phrase.

### 3.2 Typography

| Role | Family | Size | Weight and use |
| --- | --- | --- | --- |
| page title | `font-tm-serif` | 28 px | 600, one per route |
| section title | serif in zh, sans in en | 18 px | 600, major narrative section |
| pane title | `font-tm-mono` | 10 px | 600, uppercase, 0.06 em tracking |
| body | `font-sans` | 12 px | normal explanation copy |
| control | `font-tm-mono` | 11 px | 600, action and input value |
| table/data | `font-tm-mono` | 11 px | tabular numbers where applicable |
| label | `font-tm-mono` | 10 px | 600, uppercase, 0.06 em tracking |
| caption | `font-sans` | 10.5 px | secondary help, never below 10 px |
| KPI value | `font-tm-mono` | 18 px | tabular numbers |

Do not introduce another arbitrary pixel size. A new role requires a catalog
change and a reference-page specimen before production use.

### 3.3 Geometry and density

- Radius: 0 px by default. A 2 px radius is allowed for focus-sensitive compact
  controls. Consumer-card radii are forbidden in workstation routes.
- Borders: one-pixel hairlines. Do not stack nested full rectangles where one
  shared divider communicates the hierarchy.
- Control heights: 24 px extra compact, 28 px compact, 32 px standard, 36 px
  top-level mobile action. Do not create intermediate heights.
- Data rows: 32 px compact, 36 px standard, 44 px expanded or touch-friendly.
- Spacing: 4, 8, 12, 16, 24, and 32 px. Dense tables may use 6 px vertical
  padding only as an explicit row-density rule.
- Keyboard focus: 2 px `--tm-accent` outline with 1 px offset via
  `:focus-visible`; focus never changes layout geometry.
- One screen has one filled green primary action. Other actions use outline,
  ghost, or negative treatments according to their effect.

## 4. Canonical asset taxonomy

### 4.1 Layout

- `AppShell`: topbar, sidebar, mobile navigation, and content viewport.
- `TmScreen`: continuous workstation floor and route-level pane stack.
- `WorkbenchHeader`: eyebrow, 28 px title, explanation, operational status,
  and optional single primary action.
- `TmSubbar`: compact context, filters, freshness, and non-primary actions.
- `DecisionStrip`: current verdict plus the minimum decisive metrics.
- `TmPane`: flat section with optional title and metadata.
- `TmCols2`: responsive split pane. It collapses before content becomes
  unreadable and never forces two columns on narrow screens.

### 4.2 Actions and inputs

- `TmButton`: `primary`, `secondary`, `ghost`, and `danger`; `xs`, `sm`, and
  `md`; truthful `loading` and `disabled` states. `TmIconButton` requires an
  accessible name and preserves the 24 px icon-action target. `TmLinkButton`
  gives navigation the same hierarchy without pretending a link is a mutation.
- `TmDisclosureButton`: one full-width, 32 px disclosure row with explicit
  `aria-expanded`, focus treatment, reduced-motion behavior, and optional
  right-aligned scope metadata.
- `TmRowButton`: semantic full-row action for dense ledgers and selectable
  evidence rows. Callers own layout while the primitive owns hover, focus,
  disabled, and keyboard behavior.
- `TmToggleGroup`: exclusive compact choices with radio semantics, roving
  keyboard focus, and the 24 or 28 px control-height scale.
- `TmFieldShell`: label, required marker, hint, and error relationship.
- `TmInput`, `TmNumberInput`, `TmSelect`, `TmTextarea`, and `TmCheckbox`:
  standard and compact density, visible focus, programmatic labels, hint, and
  error connections. Numeric units remain visible through an affixed suffix.
- `TmRange` provides a visible current value, label and hint relationship,
  semantic token track, and native keyboard slider behavior.
- `TmSelectMenu` is the rich-option listbox exception for metadata-bearing
  options. It uses a portal, viewport clamping, disabled-option skipping,
  Arrow/Home/End movement, Enter/Space selection, Escape close, and trigger
  focus restoration. Plain choices continue to use native `TmSelect`.
- Future `TmRadio`, `TmSwitch`, and `TmCombobox` must reuse the
  same field shell and focus grammar before page adoption.

### 4.3 Navigation and data display

- `SegmentedTabs`: semantic tablist with selected state, keyboard arrow
  navigation, `aria-controls`, and no route-level primary-action styling.
- `TmPagination`: previous, next, page position, total rows, and page-size
  selector. Page-size changes return to page one unless the caller documents a
  different stable-anchor behavior.
- `TmBadge`: neutral, positive, warning, negative, and info tones with visible
  label text.
- `TmTable` and its compositional head, body, row, header, and cell assets
  provide compact or standard density, tabular numbers, `aria-sort`, and a
  selected-row grammar. `TmKpiGrid` and `TmDefList` share the same data roles.

### 4.4 Feedback, overlays, and charts

- `TmStatePane`: loading, empty, error, unauthorized, stale, and partial states
  without collapsing the pane. Recovery is local and explicit.
- Toasts announce completed transient actions. Persistent or decision-changing
  information remains in the pane or ledger and is not toast-only.
- `TmDialog` and `TmDrawer` provide portal layering, focus entry and trap,
  Escape and overlay close, scroll lock, and focus restoration through the
  shared `useTmModalFocus` contract. A dialog interrupts for a bounded
  decision; a drawer preserves page context for a short side task.
- Every chart uses semantic tokens, a text summary, stable loading/empty/error
  geometry, responsive measurement, and accessible legend text.

## 5. Operating patterns

### 5.1 Async lifecycle

| State | Required presentation | Required action |
| --- | --- | --- |
| loading | skeleton or progress copy inside stable pane | cancel only when supported |
| empty | what is absent and why it matters | one concrete next step |
| error | affected operation and recoverable cause | retry or configuration route |
| unauthorized | required permission or account state | sign in or request access |
| stale | last known timestamp and consequence | refresh |
| partial | what succeeded and what is unavailable | retry affected evidence only |

Any operation longer than one second narrates its stage at the user's current
focus. An indefinite spinner without copy is invalid.

### 5.2 Lists, tables, and selection

- The whole row selects or opens detail when that behavior is safe. Inline
  controls stop propagation and have their own accessible names.
- Selected rows use background, rule, and `aria-selected`, not color alone.
- Sorting exposes field and direction. The default sort is stated near the
  table and is stable across refreshes.
- Filters apply within the visible scope. A run-scoped list never silently
  changes to global scope.
- Pagination preserves filters and selection where the selected object remains
  in scope. Empty pages step back to the last valid page.
- Large ledgers use bounded pages or virtualization. They do not extend the
  document height in proportion to backlog size.

### 5.3 Mutations and recovery

- Destructive actions use `danger`, state their target, and require deliberate
  confirmation only when undo is unavailable.
- Reversible state changes prefer immediate feedback plus undo.
- A loading button retains its width, announces `aria-busy`, and cannot be
  triggered twice.
- Disabled controls explain the prerequisite in nearby text or a tooltip.
- Toast success never replaces a durable audit record for decision-changing
  operations.

## 6. Living `/reference` page

The reference route is part of the product, not developer-only documentation.
It uses the real locale and theme providers and contains:

1. **Foundations**: semantic colors, typography roles, spacing, density,
   borders, radius, focus, and motion.
2. **Layout**: header, subbar, decision strip, panes, split panes, and responsive
   behavior.
3. **Controls**: every button, field, selection, tab, and future form control in
   default, hover, focus, loading, disabled, and error states.
4. **Data display**: badges, KPI cells, definitions, table rows, pagination,
   expression/code blocks, and expandable evidence.
5. **Feedback**: all async states, inline messages, banners, toast rules, and
   local recovery patterns.
6. **Overlays and charts**: focus rules, chart palette, legend, tooltip, empty
   frame, and reduced-motion examples.
7. **Operating patterns**: list selection, sorting, filtering, pagination,
   destructive actions, long-running tasks, and audit-ledger behavior.
8. **Migration status**: legacy asset, canonical replacement, owner, and
   remaining consuming routes.

Examples use clearly labelled sample data. They never masquerade as live market
or account state.

## 7. Compatibility and exceptions

- Authentication pages may use a centered, lower-density layout, but they share
  the canonical button, field, feedback, typography, and semantic tokens.
- Reports may apply print-specific colors and page-break rules. Interactive
  report controls remain canonical workstation controls.
- Native input semantics are preferred. A custom combobox or select is allowed
  only when search, multi-select, or rich option content requires it.
- Mobile remains usable and accessible, but desktop at 1440 × 900 and
  1672 × 941 is the primary geometry acceptance target.
- A page-specific deviation must name the user need, route, owner, and removal
  condition in this catalog.

## 8. Migration order and completion evidence

1. Foundations: remove undefined token references and freeze type, radius,
   spacing, focus, and control-height roles.
2. Primitives: consolidate button, field, badge, pagination, and state pane.
3. High-frequency behavior: tabs, tables, list rows, tooltips, and overlays.
4. Charts: semantic token adapter plus stable state and text summary.
5. Route migration: replace raw controls in bounded route batches, beginning
   with components shared by the most routes.
6. Legacy removal: delete old assets only after consumer searches are empty.

### 8.1 Active migration ledger, 2026-08-24

| Category | Canonical asset | Migrated production surfaces | Remaining evidence |
| --- | --- | --- | --- |
| Buttons | `TmButton`, `TmIconButton`, `TmLinkButton`, `TmDisclosureButton`, and `TmRowButton` | Auth, BRAIN, Backtest, Alerts, Settings, Alpha, Report, Screener, Picks, Paper, Evolution, Factor Lab, Factors, Stock, and shared shell | executable audit reports zero unexplained native controls; only canonical `SegmentedTabs` and toast internals remain |
| Fields | `TmInput`, `TmNumberInput`, `TmSelect`, `TmSelectMenu`, `TmTextarea`, `TmCheckbox`, and `TmRange` | Auth, Backtest, Settings, Alpha, Alerts, Report, Screener, Picks, Signal, BRAIN, and `/reference` | executable audit reports zero unexplained native fields |
| Exclusive toggle | `TmToggleGroup` | Topbar locale/theme; BRAIN audit filters; Alerts severity and relevance filters | replace any future local exclusive selector before adding a page-local style |
| Pagination | `TmPagination` | Screener factor picker; Evolution proposals; BRAIN results; `/reference` | repository scan shows no separate local pagination implementation |
| State feedback | `TmStatePane` | `/reference`; Alerts; Backtest evidence; Data; Methodology; Paper attribution and positions; Signal charts and tables | legacy truncation-only copy remains allowed, but lifecycle state must not collapse geometry |
| Tooltip | `TmTooltip` | compatibility `HoverTip` and `InfoTooltip`; `/reference`; BRAIN evidence and official metric explanations | native `title` is limited to 35 truncation or compatibility hints and is protected by the no-growth audit budget |
| Charts | `chartTokens`, `TM_CHART_SERIES_CSS`, and `tmChartColorWithAlpha` | `/reference`; Backtest; BRAIN PnL; Factors; Evolution; Stock radar, price, and intraday | the monthly heatmap keeps its data-driven cell ramp as an explicit semantic-matrix exception |
| Overlays | `TmDialog`, `TmDrawer`, and `useTmModalFocus` | `/reference`; Alpha example library; simulated-order drawer | browser verification covers focus entry, Escape, trap, and trigger-focus restoration |
| Tables | `TmTable` compositional family | all standard production tables, including Picks, Paper, BRAIN yearly evidence, Backtest history, Alerts timeline, Screener, Evolution, Factor Lab, and Stock detail | no unexplained page-local standard table remains; `TmMonthlyReturnsHeatmap` retains a native matrix table for sticky axes, 2D cell color, and border-separated heatmap geometry, with an accessible caption and canonical tooltips |

Counts are static migration evidence, not a command to replace semantic row
buttons or native form elements mechanically. Each remaining control is first
classified by interaction role, then mapped to a canonical asset or recorded as
an explicit native exception.

Completion requires all of the following evidence:

- `/reference` renders every canonical component and required state.
- Production pages import canonical assets for all migrated categories.
- Static inventory shows no unexplained legacy button, card, pagination,
  tooltip, or async-state implementation.
- TypeScript, lint, focused component tests, and production build pass.
- Browser screenshots and interaction checks pass in dark/light and zh/en at
  1440 × 900 and 1672 × 941, plus a narrow viewport usability check.
- Keyboard-only focus, tab order, error recovery, and overlay close/restore are
  verified in a real browser.

Run `npm run audit:design-system` before every frontend release. The AST audit
rejects unexplained native controls and standard tables, and rejects growth
beyond the recorded native-title compatibility budget.

## 9. Ten-principles re-check

| Principle | Concrete design-system decision |
| --- | --- |
| Intent alignment | Page composition and operating patterns put the next valid action next to its prerequisite evidence. |
| Cognitive load | One taxonomy, one control meaning, one type scale, and one primary action replace route-local choices. |
| Status visibility | `WorkbenchHeader`, `TmStatePane`, and loading buttons expose state at the affected surface. |
| Forgiveness | Local retry, undo where available, stable state, and explicit recovery replace dead ends. |
| Affordance | Canonical buttons, tabs, rows, and pagination carry the same visual and keyboard meaning everywhere. |
| Design disappears | Flat geometry and limited decoration keep evidence more prominent than chrome. |
| No manual needed | Labels, hints, empty states, disabled prerequisites, and operating examples explain the workflow in place. |
| Respect time | Density, bounded ledgers, stable pagination, and stage narration reduce waiting and scanning cost. |
| No dark patterns | Defaults, thresholds, stale data, missing evidence, and sample content are explicitly labelled. |
| One primary action | Only `TmButton variant="primary"` may be filled green, once per screen context. |

Traceability remains a platform-wide invariant: status and recommendations are
linked to a run, event, timestamp, or input parameters when available, and the
UI does not invent causal explanations.

## 10. Cross-cutting conventions audit

| Convention | Required check |
| --- | --- |
| i18n | User-facing product copy comes from typed zh/en keys or caller-provided localized labels. |
| Fonts | Serif is reserved for narrative hierarchy; mono for controls/data; sans for explanation. |
| Layout | Dashboard routes use `TmScreen` and shared workbench composition. |
| Sidebar | `/reference` appears under the existing Reference group in desktop and mobile navigation. |
| Theme | Every specimen and migrated route uses semantic tokens in dark and light mode. |
| State | Loading, empty, stale, unauthorized, partial, and error use the shared grammar. |
| Data semantics | Metric labels name object, horizon, direction, and sample scope where relevant. |
| Accessibility | Focus, labels, status announcements, selection, and overlays are semantic and keyboard operable. |
| Responsive | Dense desktop geometry avoids horizontal overflow; narrow mode preserves actions and status. |
| Auditability | Mutations distinguish user action from system observation and preserve durable evidence where supported. |
