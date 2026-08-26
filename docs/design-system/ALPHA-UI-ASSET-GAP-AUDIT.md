# Alpha UI asset and reference coverage gap audit

Status: evidence snapshot from the current `codex/alpha-design-system-inventory-v2` worktree, 2026-08-26. This document is an audit, not an implementation plan or a runtime visual approval.

## Scope and counting rules

- The route count is every `page.tsx` below `frontend/src/app/(dashboard)`. It is 15. The dynamic `/stock/[ticker]` page is included. `frontend/src/app/(dashboard)/factor-lab/loading.tsx` has no sibling `page.tsx`, so it is not counted as a route.
- The sidebar count is distinct `href` values in `frontend/src/components/layout/Sidebar.tsx`. It is 14. The dynamic stock page is reached from result rows and is not a sidebar item.
- The reachable-source scan starts at the 15 route pages, the dashboard/root layouts, and route-local loading/error files, then follows local static and literal dynamic imports. It excludes tests and generated API types. It reaches 234 source files in this snapshot.
- A chart implementation file must contain a chart JSX primitive, a real `lightweight-charts` `createChart` call, a raw `<svg>`, or the custom monthly heatmap cell implementation. Import-only pages, chart comments, CSS words, and data types are not chart implementations.
- The typography scan excludes comments, tests, and generated API types and checks literal Tailwind `text-[Npx|Nrem]`, CSS `font-size`, JSX/inline `fontSize`, and chart tick/legend/tooltip props. `text-xs` and `fontSize: 12` are exactly the 12px floor and are not under 12px.
- Icon counts are imported Lucide symbol declarations, source files, and unique names. A symbol imported twice is two declarations but one unique icon. Raw SVG and custom text glyphs are separate from Lucide.

## Executive findings

1. All 15 current dashboard page routes are accounted for below. The live `/reference` route currently exposes eight localized tabs: Foundations, Icons, Controls, Data, Visualizations, Feedback, Surfaces, and Patterns (`frontend/src/components/reference/DesignSystemReference.tsx:24-38`). It is a useful base, but it is not yet a complete route-asset catalog.
2. The current source contains 23 route-reachable chart implementation files and three source-only legacy chart files. The reference has one real radar specimen, four inline SVG family specimens, and a 31-row registry with live/registered/source-only status. The registry now includes the inline `/factors` and `/report` entries and labels source-only legacy files, but it still does not render most production charts.
3. The current TypeScript AST audit confirms 49 production icon names, 49 reference icon names, and zero missing names (`frontend/scripts/audit-design-system.mjs:91-99,133-144`). The earlier 48 figure was a scanner defect that dropped the single-character identifier `X`; the design-system catalog's 49-glyph statement (`docs/design-system/ALPHA-DESIGN-SYSTEM-ASSET-CATALOG.md:48`) is correct for the current complete runtime/reference union.
4. There are three raw SVG source files and no literal `<canvas>` tags. Two files are production visualizations (`SmokePane` and `EvolutionObservatory`); the third is the reference family specimen. The stock charts use `lightweight-charts`, which owns its internal canvas and therefore does not appear as a raw `<canvas>` tag.
5. No reachable or source-only file currently contains a visible typography value below 12px under the stated scan. This is a current zero result, not proof that every browser-computed style or third-party canvas label is 12px.
6. There are zero hard-coded taxonomy-heading literals in `frontend/src/components/reference`. Two visible non-reference `DATA.*` pane headings bypass the locale map: `methodology/page.tsx:380` and `data/DataSourcesCard.tsx:52`. A broader scan finds 107 literal `TmPane title=` values outside reference, including loading/fallback and operational IDs; those are migration leads, not all confirmed i18n defects.
7. `--tm-*` tokens and the legacy palette are still additive namespaces. The tm chart adapters are coherent, but source-only `ICTimeseriesChart` still uses legacy `--border`, `--muted`, `--card-bg`, and `--accent`, and nine raw Tailwind color utility occurrences remain in three files.

## 1. Route and distinctive-asset inventory

| Route | Route source | Distinctive reusable or bespoke visual elements | Current `/reference` representation and gap |
| --- | --- | --- | --- |
| `/alerts` | `frontend/src/app/(dashboard)/alerts/page.tsx` | `AlertWorkbench`: decision strip, queue/severity filters, ranked alert rows, selected-alert inspector, evidence timeline, portfolio impact, action controls, and audit ledger. `AlertTimeline` adds filter/select/table chronology. | Controls, data, feedback, and patterns are represented in isolation. No three-column triage workbench, audit-ledger, selected-row, or alert severity specimen. |
| `/alpha` | `frontend/src/app/(dashboard)/alpha/page.tsx` | `HypothesisInputCard`, history/example drawers, `AlphaResearchContext`, `VerdictBar`, expression/AST evidence, `SmokePane` custom factor-vs-benchmark SVG, analytics accordion, and experiment ledger. | State panes, controls, and tables are partial. `SmokePane` is a registry row only; no live smoke-chart specimen, AST/evidence composition, or ledger pattern. |
| `/backtest` | `frontend/src/app/(dashboard)/backtest/page.tsx` | Context header, sticky form, verdict/comparison strips, 2:1 evidence grid, equity-plus-drawdown chart, validation gate, walk-forward chart, four grouped analytics accordions, recent-runs table, and comparison tray. | Chart family samples and generic controls exist. No 2:1 backtest shell, validation-gate composition, chart-state frame, grouped diagnostics, or recent-run action specimen. |
| `/brain` | `frontend/src/app/(dashboard)/brain/page.tsx` | `BrainMiningPanel`: run composer, funnel/progress states, scoped pagination, candidate table/audit, copy/submit/retry actions, and `BrainPnLChart` kind switch. | Controls, feedback, and table primitives are represented. No run-scoped mining workbench, candidate-audit composition, progress funnel, or PnL chart specimen. |
| `/data` | `frontend/src/app/(dashboard)/data/page.tsx` | `UniverseCard` coverage/status bars and sector/cap cells, `DataSourcesCard` provider table/freshness, `OperandCatalog` filterable operator/field catalog, loading/error panes. | Data badges/KPIs/tables are partial. No coverage-meter/ramp, source-freshness table, operator-catalog filter, or missing-data explanation specimen. |
| `/evolution` | `frontend/src/app/(dashboard)/evolution/page.tsx` | `EvolutionObservatory`: freshness/health header, decision strip, IC trend with annotations/events, reliability calibration, adaptive weights, promotion funnel, proposal/history tables, and custom health SVG sparkline. Factor-lab proposal/history components are mounted here. | Chart family and table samples exist. No annotated IC chart, calibration contract, proposal review/funnel, health sparkline, or rollback ledger specimen. |
| `/factors` | `frontend/src/app/(dashboard)/factors/page.tsx` | Factor Zoo header/subbar, KPI strip, ranking lists, inline Recharts distribution `BarChart` and activity `AreaChart`, decay/stale alerts, custom correlation line, direction-mix bars, catalog sort/filter/action rows, and correlation-matrix cells. | Generic line/bar family SVGs exist, but no real Factor Zoo distributions, timeline, matrix, stale/decay state, or row-action specimen. |
| `/methodology` | `frontend/src/app/(dashboard)/methodology/page.tsx` | Tabbed data/operators/backtest guide, KPI overview, five-stage data pipeline, sector/schema tables, bias-guard disclosures, operator/metric catalogs, portfolio-rule formulas/code blocks, and inline recovery states. | Controls and data tables are partial. No pipeline-stage, bias-disclosure, formula/code, catalog-filter, or methodology composition specimen. |
| `/paper` | `frontend/src/app/(dashboard)/paper/page.tsx` | `PaperScreen` onboarding/tour, recommendations/positions/source evidence, `PaperCurvePane` portfolio-vs-benchmark chart, simulate-order drawer/form, L2 evidence, stale/auth/error states, and tabs. | Dialog/drawer and controls have isolated samples. No tour/onboarding, paper curve, order form, evidence-source, or stale/auth composition specimen. |
| `/picks` | `frontend/src/app/(dashboard)/picks/page.tsx` | `PicksBrowser`, onboarding banner, recommendation cards/table, `BasketEdgeStrip`, conviction/grade bands, watchlist stars, refresh/progress, tooltips, and paper/stock links. | Data/control patterns are partial. No recommendation row/card, confidence/grade band, basket edge bar, onboarding, or refresh-progress specimen. |
| `/reference` | `frontend/src/app/(dashboard)/reference/page.tsx` | `DesignSystemReference` currently mounts eight localized reference sections. `ReferenceIconography` lists 49 Lucide icons; `ReferenceVisualizations` mounts a real radar plus line/bar/heat/drawdown SVG families and a 31-row registry with live/registered/source-only status. | This is the catalog itself. It needs the complete taxonomy and live specimens called out in the matrix below. |
| `/report` | `frontend/src/app/(dashboard)/report/page.tsx` | Picker/config/examples/zoo, compare overlay, report cover/KPIs/risk/tail/yearly tables, `FactorPnLChart`, `TmDrawdownChart`, `TmMonthlyReturnsHeatmap`, `TmICTimeseriesChart`, `TmExposureChart`, `TmCompareEquityChart`, inline correlation `LineChart`, momentum/overlap/recovery, and deep modal. | The 31-row registry now maps the report charts correctly and marks them registered. There is still no live comparison, IC, exposure, heatmap, drawdown, or modal composition specimen. |
| `/screener` | `frontend/src/app/(dashboard)/screener/page.tsx` | Factor picker with pagination, universe/sector/combine controls, results/watchlist table, sector/cap mix bars, aggregate contribution bars, diagnostics, stale/error/empty states, and glyph-based disclosure/sort controls. | Generic controls/tables and state panes exist. No factor-picker/results workbench, mix/contribution bars, or diagnostics composition specimen. |
| `/settings` | `frontend/src/app/(dashboard)/settings/page.tsx` | BYOK/credential card with connection test, signal-weight editor, watchlist editor, change log, danger actions, toggles, and status banners. | Controls and feedback are isolated. No credential-test, destructive-action, change-log, or settings form composition specimen. |
| `/stock/[ticker]` | `frontend/src/app/(dashboard)/stock/[ticker]/page.tsx` | `PriceChart` uses `lightweight-charts` for candles, volume, SMA, markers, and crosshair; `IntradayDrawer` drills into intraday data; `AttributionRadar` uses `TmRadarChart`; profile/fundamentals/catalysts/thesis/sources/explain panels and not-found/error states. | Radar is represented directly. Price/intraday interactions, marker/tooltip contract, chart empty/error frame, and stock-detail composition are not represented. |

Sidebar verification: the 14 hrefs are `/picks`, `/paper`, `/alerts`, `/alpha`, `/backtest`, `/screener`, `/report`, `/factors`, `/evolution`, `/brain`, `/data`, `/methodology`, `/reference`, and `/settings` (`frontend/src/components/layout/Sidebar.tsx`). The dynamic stock route is the only current page route outside that list.

## 2. Chart and graph inventory

Current chart count by implementation file:

- 23 route-reachable files: 17 Recharts files, two `lightweight-charts` files, two production raw-SVG files, one custom table/cell heatmap, and the reference raw-SVG specimen file. `TmRadarChart` is one of the 17 Recharts files and is reused by stock detail and reference. The repository audit script separately reports 25 string-detected visualization assets because it includes comment-only `ExplainRangePanel` and does not recognize the custom table heatmap; the construct-based count here is the chart count.
- Three source-only legacy Recharts files: `frontend/src/components/backtest/DrawdownPane.tsx`, `frontend/src/components/backtest/EquityCurvePane.tsx`, and `frontend/src/components/signal/ICTimeseriesChart.tsx`.
- Three raw `<svg>` files exactly: `frontend/src/components/alpha/SmokePane.tsx:205`, `frontend/src/components/evolution/EvolutionObservatory.tsx:292`, and `frontend/src/components/reference/ReferenceVisualizations.tsx:107`. Literal `<canvas>` count is zero.
- Actual `lightweight-charts` `createChart` calls occur in `frontend/src/components/stock/PriceChart.tsx` and `frontend/src/components/stock/IntradayDrawer.tsx`. `ExplainRangePanel` mentions the library in a comment but does not create a chart.

| Family / implementation | Source path and current route | Reference status |
| --- | --- | --- |
| Factor Zoo distribution bars and activity area | `frontend/src/app/(dashboard)/factors/page.tsx:904-1048`, `/factors`; Recharts `BarChart` and `AreaChart`, plus custom direction/correlation/matrix bars | Family SVG only. Actual route-specific charts and empty/stale states are absent. |
| Report rolling correlation | `frontend/src/app/(dashboard)/report/page.tsx:1444-1525`, `/report`; inline Recharts `LineChart` with zero/high-correlation reference lines | Registry row at `ReferenceVisualizations.tsx:44`; registered, no live chart specimen. |
| Alpha smoke equity paths | `frontend/src/components/alpha/SmokePane.tsx:205-213`, `/alpha`; raw SVG with train/OOS split and factor/benchmark paths | Registry row only; no live production specimen. |
| Underwater drawdown | `frontend/src/components/backtest/TmDrawdownChart.tsx:49-115`, `/report`; Recharts `AreaChart` | Registry row at `ReferenceVisualizations.tsx:38` correctly says `report`; registered, no live specimen. |
| Equity plus drawdown | `frontend/src/components/backtest/TmEquityDrawdownChart.tsx:71-193`, `/backtest`; Recharts `ComposedChart` | Registry row at `ReferenceVisualizations.tsx:33` correctly says `backtest`; `/paper` uses `PaperCurvePane`, which has its own row. |
| Monthly returns heatmap | `frontend/src/components/backtest/TmMonthlyReturnsHeatmap.tsx:42-140`, `/report`; custom year-by-month cells and semantic return ramp | Registry row at `ReferenceVisualizations.tsx:39` correctly says `report`; registered, no live specimen. |
| Train/test split | `frontend/src/components/backtest/TrainTestSplitPane.tsx:29-168`, `/backtest`; Recharts `ComposedChart` with split boundary | Registry row exists; no live specimen or split/legend contract. |
| Turnover distribution | `frontend/src/components/backtest/TurnoverProfilePane.tsx:29-169`, `/backtest`; Recharts `BarChart` plus KPI rows | Registry row exists; no live specimen. |
| Walk-forward IC bars | `frontend/src/components/backtest/WalkforwardPane.tsx:53-179`, `/backtest`; Recharts `BarChart` and threshold line | Registry row exists; no live specimen or threshold annotation contract. |
| Win/loss histogram | `frontend/src/components/backtest/WinLossDistributionPane.tsx:42-178`, `/backtest`; Recharts `BarChart` plus KPI rows | Registry row exists; no live specimen. |
| BRAIN PnL | `frontend/src/components/brain/BrainPnLChart.tsx:52-103`, `/brain`; Recharts `LineChart` with chart-kind variants | Registry row exists; no live specimen or variant legend. |
| Factor PnL | `frontend/src/components/charts/FactorPnLChart.tsx:85-260`, `/report`; multi-line Recharts `LineChart` for factor/benchmark | Registry row at `ReferenceVisualizations.tsx:40` correctly says `report`; registered, no live specimen. |
| Equity comparison | `frontend/src/components/charts/TmCompareEquityChart.tsx:65-142`, `/report`; multi-line Recharts `LineChart` | Registry row at `ReferenceVisualizations.tsx:41` correctly says `report`; registered, no live specimen. |
| Attribution radar | `frontend/src/components/charts/TmRadarChart.tsx:21-83`, `/stock/[ticker]` and `/reference`; dynamic Recharts `RadarChart`, positive/negative split, text summary | Direct real-production specimen in `ReferenceVisualizations.tsx:51-62`; this is the strongest current coverage. |
| Evolution IC trend | `frontend/src/components/evolution/IcTrendChart.tsx:180-295`, `/evolution`; Recharts `LineChart`, event and annotation markers | Registry row exists; no live specimen with annotations/events. |
| Reliability calibration | `frontend/src/components/evolution/ReliabilityChart.tsx:57-160`, `/evolution`; Recharts calibration `LineChart` | Registry row exists; no live specimen or empty-calibration frame. |
| Paper curve | `frontend/src/components/picks/paper/PaperCurvePane.tsx:20-63`, `/paper`; Recharts `ComposedChart` portfolio/benchmark | Registry row exists; no live specimen. |
| Legacy IC timeseries | `frontend/src/components/signal/ICTimeseriesChart.tsx:17-59`, source-only; legacy Recharts `ComposedChart` using `--border`, `--muted`, `--card-bg`, `--accent` | Registry row at `ReferenceVisualizations.tsx:54` correctly marks `source-only`; no current caller. Either retire or migrate; do not treat it as route coverage. |
| Exposure | `frontend/src/components/signal/TmExposureChart.tsx:38-150`, `/report`; two horizontal Recharts `BarChart` views for sector/cap exposure | Registry row at `ReferenceVisualizations.tsx:43` correctly says `report`; registered, no live specimen. |
| IC timeseries | `frontend/src/components/signal/TmICTimeseriesChart.tsx:39-141`, `/report`; Recharts `ComposedChart` with IC bars and rolling mean | Registry row at `ReferenceVisualizations.tsx:42` correctly says `report`; registered, no live specimen. |
| Daily stock price | `frontend/src/components/stock/PriceChart.tsx:31-324`, `/stock/[ticker]`; `lightweight-charts` candlestick, volume histogram, SMA, markers, crosshair, and tooltip | Registry row exists; no live interactive specimen or marker/tooltip state. |
| Intraday drill-down | `frontend/src/components/stock/IntradayDrawer.tsx:33-320`, `/stock/[ticker]`; `lightweight-charts` intraday line/candle view inside drawer | Registry row exists; no live drawer-plus-chart specimen. |
| Evolution health sparkline | `frontend/src/components/evolution/EvolutionObservatory.tsx:292-296`, `/evolution`; raw SVG polyline | Registry row exists; no live specimen or textual fallback contract. |
| Reference family miniatures | `frontend/src/components/reference/ReferenceVisualizations.tsx:132-142`, `/reference`; raw SVG line, bar, heat, and drawdown family examples | Direct family specimens exist, but they are illustrative SVGs rather than the production chart implementations. |
| Legacy drawdown pane | `frontend/src/components/backtest/DrawdownPane.tsx:14-179`, source-only; legacy Recharts `AreaChart` | Registry row at `ReferenceVisualizations.tsx:53` explicitly marks `source-only`; no current route caller. |
| Legacy equity pane | `frontend/src/components/backtest/EquityCurvePane.tsx:13-179`, source-only; legacy Recharts `LineChart` | Registry row at `ReferenceVisualizations.tsx:52` explicitly marks `source-only`; no current route caller. |

Non-library graph-like visual primitives also need coverage, even though they are not counted as chart implementation files: `UniverseCard` coverage meters (`frontend/src/components/data/UniverseCard.tsx:203,284,314`), Factor Zoo decay/direction/correlation bars (`frontend/src/app/(dashboard)/factors/page.tsx:822-885`), Screener sector/cap/contribution/eligibility bars (`frontend/src/app/(dashboard)/screener/page.tsx:1459-1729`), `RatingBadge` aggregation bar (`frontend/src/components/stock/RatingBadge.tsx:74`), `RefreshButton` progress (`frontend/src/components/picks/RefreshButton.tsx:70`), and `TmField` range track (`frontend/src/components/tm/TmField.tsx:457`). They now have registry rows at `ReferenceVisualizations.tsx:55-59`, but no specimen defines their scale, zero/unknown behavior, or accessible text contract.

## 3. Iconography and custom glyphs

### Exact counts

| Source | Count | Evidence |
| --- | ---: | --- |
| Lucide import declarations | 164 | Static named-import scan across non-test frontend source; the AST audit uses the same names |
| Files importing Lucide | 45 | Same scan |
| Unique Lucide names, complete source/runtime union including `/reference` | 49 | AST audit output: `production icons: 49, reference icons: 49, missing: 0` |
| Unique Lucide names, strict non-reference source | 48 | The only additional complete-union name is `Trash2`, imported by reference controls |
| Unique Lucide names, current route-reachable non-reference pages | 47 | `Filter` is only in unmounted `AlertTimeline`; `Trash2` is reference-only |
| Reference registry names | 49 | `ReferenceIconography.tsx:13-38`; exact set matches the complete union |
| Raw `<svg>` files | 3 | `SmokePane`, `EvolutionObservatory`, `ReferenceVisualizations` |
| Raw `<canvas>` files | 0 | No literal canvas tag; stock charts use the library internally |
| Actual `lightweight-charts` files | 2 | `PriceChart`, `IntradayDrawer` |

The complete current Lucide set is: `AlertCircle`, `AlertTriangle`, `ArrowDown`, `ArrowRight`, `ArrowUp`, `BellRing`, `Bookmark`, `Check`, `CheckCircle`, `CheckCircle2`, `ChevronDown`, `ChevronRight`, `ChevronUp`, `CircleHelp`, `Clipboard`, `Clock3`, `Compass`, `Cpu`, `ExternalLink`, `Filter`, `FlaskConical`, `Gauge`, `HelpCircle`, `History`, `Inbox`, `Info`, `LayoutGrid`, `Library`, `Loader2`, `Lock`, `LogIn`, `LogOut`, `MousePointerClick`, `Pencil`, `Play`, `RefreshCw`, `RotateCcw`, `Save`, `Send`, `ShieldAlert`, `ShieldCheck`, `Sparkles`, `Square`, `Star`, `Trash2`, `UserCircle`, `Wallet`, `X`, and `XCircle`.

The 48-versus-49 discrepancy has two separate causes that must not be conflated: (1) a regex requiring two characters omitted the valid single-letter icon `X`; and (2) a strict non-reference source scan excludes `Trash2`, which is currently imported by `ReferenceControls` and therefore belongs to the complete `/reference` runtime union. The strict current page-only non-reference set is 47 because `Filter` is imported by the unmounted `AlertTimeline` source file. No name is missing from the 49-name reference registry.

### Semantic groups and coverage gaps

- Navigation and context: `Compass`, `LayoutGrid`, `ChevronDown`, `ChevronRight`, `ChevronUp`, `LogIn`, `LogOut`, `UserCircle`, `ExternalLink`, and `MousePointerClick`. Sources include `SidebarAuthSlot`, `TmSelectMenu`, `TmPagination`, `TmField`, `ReportDeepModal`, and stock chart affordances. Reference lists glyphs but does not show navigation, disclosure, pagination, or external-link contexts.
- Mutation and workflow: `Play`, `Save`, `RefreshCw`, `RotateCcw`, `Send`, `Pencil`, `Trash2`, `X`, `Square`, `Check`, `ArrowUp`, `ArrowDown`, and `ArrowRight`. Sources include backtest form, factor lab, BRAIN, settings, drawers, and table rows. Reference has no mutation/disabled/loading grouping or destructive-versus-reversible examples.
- Status, feedback, and permission: `AlertCircle`, `AlertTriangle`, `BellRing`, `CheckCircle`, `CheckCircle2`, `Clock3`, `Info`, `Loader2`, `ShieldAlert`, `ShieldCheck`, and `XCircle`. Sources include `AlertWorkbench`, `TmStatePane`, `Toast`, backtest gates, BRAIN audit, and onboarding. Reference has state panes, but not toast, queue severity, permission, or audit contexts.
- Research and data context: `Bookmark`, `Clipboard`, `Cpu`, `Filter`, `FlaskConical`, `Gauge`, `HelpCircle`, `CircleHelp`, `History`, `Inbox`, `Library`, `Lock`, `Sparkles`, `Star`, and `Wallet`. Sources include factor history, methodology/data catalogs, stock explain/thesis, picks, and paper. Reference does not connect these icons to data-source, favorites, evidence, or lock semantics.

The current reference rules (`frontend/src/components/reference/ReferenceIconography.tsx:57-68`) document 14px inline, 16px standard-control, and 20px standalone-status sizes, Lucide's 2px default stroke, and accessible names for icon-only actions. Production call sites still use a range of `h-3`/`w-3` (12px), `h-3.5` (14px), `h-4` (16px), `h-5` (20px), `h-6` (24px), and `h-7` (28px), with local `strokeWidth={1.2}`, `1.5`, `1.75`, `1.8`, or `2`. Examples are `TmSelectMenu.tsx:184-185`, `SidebarAuthSlot.tsx:28-46`, `AlertWorkbench.tsx:282,387`, `BacktestFormSticky.tsx:371`, and `BrainMiningPanel.tsx:1971-1973`. These may be legitimate context variants, but the reference needs an explicit size/stroke matrix and an audit of exceptions. Filled states are also local exceptions, for example `WatchlistStar.tsx:10-12` and `AlphaExperimentLedger.tsx:41`; the catalog should show favorite/selected fill rather than treating it as a new icon family.

Non-Lucide glyphs bypass the icon registry and need an explicit text/glyph boundary:

- Navigation markers: `Sidebar.tsx:117,127` uses `▶`, `·`, `▾`, and `▸`; `TmButton.tsx:222` uses `▸`; `Topbar.tsx:73` uses `▲`.
- Pagination and disclosure: `screener/page.tsx:677,686,1305` uses `←`, `→`, `▾`, and `▸`; the same page passes `✕` as an icon at lines 839 and 867.
- Sort/status symbols: `factors/page.tsx:1265` uses `▲`, `▼`, and `·`; `factors/page.tsx:1363` uses `⚠`; `screener/page.tsx:580,1268` and `report/page.tsx:1364,1392` use `·` as a table/sort placeholder; translated warning strings also contain `⚠` in `frontend/src/lib/i18n.ts:90,92,521` and English counterparts.
- Text separators and workflow arrows: many `·` and `→` instances are prose separators, not icons. They should remain text only when they are not interactive or status carriers. `SmokePane.tsx:213` uses `→` in a date range, while `factors/page.tsx:790` uses `▶` as a button icon and should be covered as an action-icon exception.

## 4. Visible typography floor

Exact current result: **0 under-12px occurrences in 234 reachable source files, 0 files; 0 under-12px occurrences in all non-test, non-generated frontend source, 0 files.** Therefore there are no exact file/line/value rows to report for a current under-12 visible role.

The scan includes literal arbitrary Tailwind sizes, CSS declarations, inline/JSX `fontSize`, chart tick/legend/tooltip props, and SVG label styles. It intentionally treats 12px as compliant, so current `text-xs`, chart `fontSize: 12`, and the `TM_CHART_TYPOGRAPHY` values in `frontend/src/components/charts/chartTokens.ts:25-31` are at the floor. It also cannot prove browser-computed sizes produced by third-party chart internals or inherited styles. The reference should keep a visible “12px minimum” specimen and make chart axis, legend, tooltip, SVG-label, and caption roles inspectable.

## 5. Reference taxonomy headings and locale bypasses

Taxonomy identifiers such as `FOUNDATIONS.COLOR` are architectural IDs, not user-facing copy. The source catalog defines the intended rule: reference headings must use typed locale keys, while legacy production pane IDs may pass through a compatibility map (`docs/design-system/ALPHA-DESIGN-SYSTEM-ASSET-CATALOG.md:113-120`).

- Hard-coded dotted taxonomy literals in `frontend/src/components/reference/**`: **0** in the current snapshot. `ReferenceFoundations`, `ReferenceControls`, `ReferenceDataFeedback`, `ReferencePatterns`, `ReferenceSurfaces`, `ReferenceIconography`, and `ReferenceVisualizations` all use locale keys or local bilingual copy.
- Visible non-reference `DATA.*` bypasses: **2** exact instances:
  - `frontend/src/app/(dashboard)/methodology/page.tsx:380`: `title="DATA.PIPELINE"`.
  - `frontend/src/components/data/DataSourcesCard.tsx:52`: `title="DATA.SOURCES"`.
- `frontend/src/components/data/UniverseCard.tsx:12` mentions `DATA.COVERAGE` only in a comment and is excluded from visible-heading counts.
- Broader audit lead: **107** literal `TmPane title=` values outside reference match an uppercase/dotted-or-operational-title pattern in the current source. This includes loading/error panes, route-local English labels, and reusable IDs such as `EQUITY.UNDERWATER`, `IC.TIMESERIES`, `EXPOSURE`, `SIGNAL.FORM`, `REPORT.COVER`, and `SETTINGS / BYOK`. It should be triaged through the compatibility map rather than blindly translated, because some are internal operational identifiers and some are visible headings.

Proposed taxonomy IDs for the complete catalog: `FOUNDATIONS`, `LAYOUT`, `ICONOGRAPHY`, `TEXT_ROLES`, `CONTROLS`, `DATA_DISPLAY`, `VISUALIZATIONS`, `STATES_RECOVERY`, `OVERLAYS`, `PATTERNS`, and `MIGRATION`. Every user-facing title in these sections should resolve through `reference.*` locale keys. Production pane IDs can remain short uppercase IDs only when their compatibility-map status is explicit and the rendered heading is localized.

## 6. Theme tokens and semantic color gaps

The tm namespace is defined in `frontend/src/app/globals.css:304-350` and exposed alongside the legacy palette in `frontend/tailwind.config.ts:12-73`.

| Token | Dark value | Light value | Current role and audit |
| --- | --- | --- | --- |
| `--tm-bg` | `#0a0c0f` | `#f3efe7` | Floor/page background. |
| `--tm-bg-2` | `#11141a` | `#fbf8f2` | Raised/header/control surface; also used by many hover utilities. |
| `--tm-bg-3` | `#19212b` | `#e8dfd0` | Documented as hover/tertiary surface; actual code also uses it as a static explanatory surface. |
| `--tm-fg` | `#e7eaf0` | `#211f1a` | Primary evidence/decision text. |
| `--tm-fg-2` | `#aab1bd` | `#4b463d` | Explanation and metadata. |
| `--tm-muted` | `#868d99` | `#6e675b` | Readable labels/captions. |
| `--tm-rule` | `#2b333e` | `#cbbfad` | Default hairline, chart grid, dividers. |
| `--tm-rule-2` | `#3b4654` | `#aa9b86` | Strong boundary, selected/emphasized rule, scrollbar hover. |
| `--tm-accent` | `#39d98a` | `#0a7344` | Interaction, focus, selection, primary action. |
| `--tm-pos` | `#9fdf6c` | `#34762a` | Favorable/validated outcome. |
| `--tm-warn` | `#f0b34a` | `#b06a06` | Incomplete, stale, review required. |
| `--tm-neg` | `#f06464` | `#b91c1c` | Failed, blocked, destructive. |
| `--tm-info` | `#6aa9ff` | `#1e63cc` | Neutral information. |

Assessment:

- `hover` and `rule` are not value-conflated: `--tm-bg-3` and `--tm-rule` are visibly distinct in both themes, and `--tm-rule-2` is distinct from `--tm-rule`. The architectural ambiguity is behavioral. The reference calls `bg-3` “hover”, while production hover classes commonly use `hover:bg-tm-bg-2` and static content boxes use `bg-tm-bg-3`. Keep the existing semantic names, but document the interaction/tertiary distinction and audit callers rather than inventing a new token.
- `--tm-rule` is correctly used for chart grids, dividers, scrollbar track, and default borders; `--tm-rule-2` is used for emphasized lines and scrollbar hover. The reference needs examples of both so a stronger rule is not mistaken for a hover fill.
- `--tm-accent` versus `--tm-pos` is intentionally distinct in the current CSS comment: emerald means interaction, while leaf green means validated performance (`globals.css:321-324`). Do not merge them. The chart adapter correctly exposes positive/negative/warning/info independently in `frontend/src/components/charts/chartTokens.ts:1-23`.
- The legacy palette remains available: `tailwind.config.ts:12-50` maps `bg`, `card`, `border`, `text`, `muted`, `accent`, `green`, `red`, `yellow`, and `purple` to the older variables. The current scan finds 51 non-tm `var(--...)` references, including font/fallback variables; the most material semantic leftovers are the legacy chart and fallback usages in `ICTimeseriesChart.tsx` and `globals.css`.
- Nine raw color utility occurrences remain in three files: sky info classes in `AlertWorkbench.tsx:56,437`, zinc fallback in `RatingBadge.tsx:47`, and red danger classes in `settings/page.tsx:552-566`. The reference should show these as migration exceptions or migrate them to `tm-info`/`tm-neg` without changing their product meaning.

## 7. Proposed complete `/reference` taxonomy

The current eight tabs can remain the navigation shell, with the following complete nested taxonomy and specimen requirements:

1. **Foundations**: dark/light semantic token swatches; `bg`, `bg-2`, `bg-3`, rule, strong rule, accent, positive, warning, negative, info; typography roles; 12px floor; spacing, row heights, border/radius, focus, motion, and print behavior.
2. **Layout**: AppShell, topbar, sidebar, route viewport, `WorkbenchHeader`, `TmSubbar`, `DecisionStrip`, `TmScreen`, `TmPane`, `TmCols2`, and the desktop 2:1/three-column workbench shells.
3. **Iconography**: all 49 Lucide glyphs; 14/16/20px role sizes; stroke matrix; filled favorite/selected exceptions; icon-only accessible-name contract; navigation/sort/warning glyph exceptions; custom SVG boundary.
4. **Text roles**: page title, section title, pane title, body, control, table/data, label, caption, KPI, chart tick, axis label, legend, tooltip, code/formula, and bilingual wrapping/abbreviation examples.
5. **Controls**: buttons and link buttons, icon buttons, inputs, number/select/rich select, textarea, checkbox, range, toggle group, segmented tabs, disclosure, pagination, filters, and row buttons. Show default, hover, focus, loading, disabled, error, and destructive variants.
6. **Data display**: badges, KPI grid, definition list, dense/standard/selected/sorted tables, pagination, code/formula blocks, coverage meters, progress/ramp bars, matrix cells, watchlist/favorite, and missing/unknown values.
7. **Visualizations**: real production radar; lightweight price/intraday; line/equity; area/drawdown; combined equity/drawdown; bar/histogram; train/test and walk-forward; IC bars plus rolling line; exposure bars; calibration; evolution/alpha SVG; paper curve; monthly heatmap; factor/report comparison; legends, tooltips, text summaries, and stable empty/loading/error/partial frames.
8. **States and recovery**: loading, empty, error, unauthorized, stale, partial, inline retry, sign-in/configure route, mutation progress, optimistic/undo, chart no-data, chart failure, and truthful long-running stages. Include `TmStatePane`, toast rules, banners, and onboarding/tour states.
9. **Overlays**: tooltip placements and keyboard/focus behavior, `InfoTooltip`/legacy tooltip aliases, `TmDialog`, `TmDrawer`, deep report modal, simulate-order drawer, close/escape/focus restoration, viewport clamping, and scroll lock.
10. **Patterns and migration**: decision-first route shell, one-primary-action rule, async lifecycle, scoped list/filter/sort/pagination, selected rows, audit ledger, comparison overlay, onboarding, mutation/recovery, source-only chart status, token exception register, and per-route asset coverage.

## 8. Prioritized coverage matrix

| Priority | Element/gap | Canonical specimen needed | Cross-page migration needed | i18n need | Severity | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| P0 | Visualization registry correctness | One row per current chart implementation with actual route, implementation type, source-only status, states, and summary contract | `/reference` registry plus every 15-route owner | Chart family names, route labels, summaries, aria labels | Release-blocking | `ReferenceVisualizations.tsx:19-60`; current 31-row mapping is accurate but most rows are registered-only |
| P0 | Production chart coverage | Live radar, price, intraday, line, area, composed, bars, IC, exposure, calibration, heatmap, SVG, and paper examples | `/stock`, `/backtest`, `/report`, `/evolution`, `/brain`, `/paper`, `/alpha`, `/factors` | Legend, axis, tooltip, empty/error text | Release-blocking | 23 route-reachable chart files; most are registry-only |
| P0 | Stable chart lifecycle | Same geometry for loading/empty/error/partial and a text summary for each family | All chart owners, especially `/backtest`, `/report`, `/stock`, `/evolution` | State copy and recovery actions | High | Catalog contract says every chart retains stable states; reference shows no chart-state specimens |
| P0 | Layout/workbench composition | AppShell, header, subbar, decision strip, pane, split grid, triage grid, and 2:1 evidence grid | All 15 routes | Header/status/action labels | High | Route table shows repeated shells; `/reference` has no dedicated layout section |
| P0 | Legacy token namespace | Side-by-side tm/legacy token audit and an explicit exception table | `ICTimeseriesChart`, legacy CSS classes, raw color utilities | Status/exception copy where visible | High | `tailwind.config.ts:12-73`; 51 non-tm vars and nine raw utilities |
| P0 | Source-only chart lifecycle | Registry rows marked source-only with retire/migrate status | `DrawdownPane`, `EquityCurvePane`, `ICTimeseriesChart` | No new copy unless rendered | High | Three files have no current route caller |
| P1 | Stock chart interaction | Candlestick/volume/SMA/marker/crosshair and intraday drill-down specimen | `/stock/[ticker]` | Marker/tooltip/empty/error copy | High | `PriceChart.tsx`, `IntradayDrawer.tsx`; no live reference sample |
| P1 | Non-library metric graphics | Coverage/progress/ramp/matrix/eligibility/conviction specimens with zero, unknown, overflow, and accessible text states | `/data`, `/factors`, `/screener`, `/picks`, `/stock`, `/brain` | Labels, unknown reasons, status text | High | Multiple inline width/background implementations listed above |
| P1 | Icon role and exception contract | 49 glyph gallery grouped by navigation/action/status/research plus 14/16/20px and fill/stroke variants | 45 importing files; glyph callers in Sidebar, Topbar, Screener, Factors | Accessible names and tooltips | Medium-high | 164 declarations, 49 complete-union names; `X` was the prior regex omission, `Trash2` is reference-only versus strict non-reference source |
| P1 | Text roles and chart floor | Inspectable role specimens at 12px minimum, including SVG/chart labels | All route-local labels and chart primitives | Bilingual role examples and wrapping | Medium-high | Current under-12 scan is 0, but the role contract is not visible in `/reference` |
| P1 | Taxonomy localization | Localized IDs for foundations/layout/text/visualization/overlay/pattern headings and compatibility-map status | Two visible `DATA.*` headings plus triaged 107 literal titles | Required for all user-facing headings | Medium | Reference literal count 0; `DATA.PIPELINE` and `DATA.SOURCES` bypass locale |
| P1 | Data/table states | Dense/standard tables, selected/sorted rows, matrix heatmap, pagination, filter/no-results, unknown/missing cells | `/alerts`, `/brain`, `/data`, `/factors`, `/methodology`, `/picks`, `/report`, `/screener`, `/settings` | Empty/filter/recovery copy | Medium-high | Current reference has a basic table but no route-specific table states |
| P1 | Overlays and transient feedback | Tooltip aliases, toast, dialog, drawer, tour, focus restoration, undo/progress | `/alpha`, `/paper`, `/report`, `/stock`, `/settings`, `/picks` | Action/result/recovery copy | Medium | Surfaces shows tooltip/dialog/drawer, but no toast/tour specimen |
| P2 | Theme side-by-side behavior | Same specimens in dark/light with token-role labels and contrast notes | All tm consumers; legacy exceptions | Locale switch must preserve hierarchy | Medium | Distinct current tm values, but legacy and tm namespaces coexist |
| P2 | Migration ledger | Per-asset status: canonical, family-only, registry-only, source-only, raw exception, or unverified runtime | All route owners | Status labels only | Medium | Existing pattern ledger is not yet exhaustive for charts/glyphs/routes |

This matrix is desktop-primary. It does not propose a mobile-first redesign; responsive behavior is only a verification state for the existing desktop workstation contract.
