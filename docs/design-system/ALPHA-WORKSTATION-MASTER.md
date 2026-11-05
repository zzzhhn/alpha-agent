# Alpha Workstation Master Design System

Status: implementation source of truth for workstation page composition

Scope: all desktop workstation routes. Authentication and print exceptions are
defined in `ALPHA-DESIGN-SYSTEM-ASSET-CATALOG.md`.

Reusable component, control, typography, state, and operating-pattern source of
truth: `ALPHA-DESIGN-SYSTEM-ASSET-CATALOG.md` and the living `/reference` route.

Reference viewport: 1672 × 941 px

Reference images: `references/alpha-workbench/proposed-*-native.png`

## 1. Product contract

AlphaCore is a decision workstation, not a generic dashboard. Each screen must let a researcher answer, in order:

1. What changed or what am I testing?
2. Is the evidence sufficient to act?
3. What is the one primary action?
4. What evidence, risk, and history support that action?

The current approved production page is the baseline for in-place refinement. Generated references define geometry only when the current request explicitly asks for that reference; they do not override later user-approved changes. Preserve real API data and honest empty, loading, stale, and error states. Never invent a successful result merely to resemble a populated reference.

## 2. Requirement boundary

- The factor reference maps to `/alpha`. `/factors` remains the separate Factor Zoo.
- Desktop is the acceptance target. Mobile remains usable but is not a 1:1 target.
- “1:1” means matching the reference frame, pane order, grid ratios, visual hierarchy, density, colors, borders, and state placement at 1672 × 941.
- Sample numbers and tickers in the generated images are illustrative. Production values come only from real state.
- New backend contracts are allowed only when they expose real freshness, health, provenance, or decision-ledger data. Missing data is shown explicitly.

## 3. Shared frame

| Element | Contract |
| --- | --- |
| App chrome | 36 px top bar, 200 px desktop sidebar, no page-level rounded canvas |
| Page background | `--tm-bg` |
| Header | 80 px nominal height, title left, compact operational context right |
| Horizontal padding | 24 px |
| Pane padding | 16 px default, 12 px for dense tables |
| Rules | 1 px `--tm-rule`; stronger divisions use `--tm-rule-2` |
| Radius | 0 to 2 px. Do not use consumer-card rounding |
| Row density | 32 to 44 px for single-line tables; multi-line alert summaries use about 84 px with five-row pagination |
| Primary action | One filled `--tm-accent` action per screen |
| Secondary actions | Outline or text actions; refresh must not compete with the primary action |
| Form controls | Use the canonical TM field family, including `TmRange` and rich-option `TmSelectMenu`; do not add route-local native styling |
| Row actions | Use `TmRowButton` for a full interactive row and keep inline actions independently named |
| Overlays | Dialogs and drawers share `useTmModalFocus`; Escape closes and focus returns to the trigger |
| Charts | SVG and canvas colors resolve from shared semantic chart tokens; every chart retains a text summary |

## 4. Typography and tokens

- Product and page titles use the current display serif treatment.
- Labels, controls, status, tables, formulas, and numeric values use `font-tm-mono` or `font-mono`.
- Labels, captions, controls, and ordinary data never render below the 12 px body baseline. Page titles are 27 to 31 px.
- Use the existing tokens in `frontend/src/app/globals.css`: `--tm-bg`, `--tm-bg-2`, `--tm-bg-3`, `--tm-fg`, `--tm-fg-2`, `--tm-muted`, `--tm-rule`, `--tm-rule-2`, `--tm-accent`, `--tm-warn`, `--tm-neg`, and `--tm-info`.
- Accent emerald means interaction, focus, selection, or the one primary action. Leaf green means a positive or validated outcome. Amber means incomplete or requires review. Red means failed or blocked. Muted text must remain readable on `--tm-bg`.

## 5. Shared composition

Every page follows this order:

1. `WorkbenchHeader`: page identity plus freshness, engine health, or run context.
2. Input or decision context strip.
3. `DecisionStrip`: current verdict and the minimum decisive metrics.
4. Primary workbench: the largest evidence view plus a contextual inspector.
5. Comparison, funnel, or diagnostic summaries.
6. Visible decision ledger.

Async panes keep useful geometry while requests are in flight. Pre-run panes may be compact, non-animated placeholders rather than full-height empty result boxes. Loading uses a skeleton inside the pane. Empty explains the next action. Error contains the error and retry in the affected pane. A single failed request must not erase unrelated controls, queue navigation, or history.

Global service status separates connectivity from pipeline freshness. A failed or timed-out pipeline check with a successful DB check means service available / data status unknown. Client timeout, offline, authentication or rate-limit failures mean connection unconfirmed, not a proven outage. Only an explicit DB-down result or a server error from the basic health probe shows service unavailable. Every visible-tab poll re-evaluates both observations without retaining a stale green state; no extra requests or retries are introduced. The `/reference` service-state catalogue includes these partial and unknown states.

## 6. Page geometry

### 6.1 Factor Alpha, `/alpha`

Reference: `proposed-factors-native.png`.

- Header: research stage, universe, and truthful data/engine state.
- Hypothesis composer: thesis input and actions beside a six-field validation panel, using existing TM controls and one green “translate and backtest” action. Examples and history remain beside the input; rerun appears after translation.
- Verdict: compact truthful pre-run strip; four metrics for IC, Sharpe, drawdown, and evidence completeness when running or showing results.
- Evidence row: three equal columns for expression/data lineage, IS/OOS validation, and falsification/risk gates.
- Ledger: visible dense recent-experiments table at the bottom of the first workbench flow.
- Required provenance indicators: input fields, lookback, lag/PIT status when returned by the service. Never fabricate PIT compliance.

### 6.2 Backtest, `/backtest`

Reference: `proposed-backtest-native.png`.

- Setup keeps a stable expression editor beside core controls. Cost, benchmark and daily-holdings opt-in remain visible in a compact summary; advanced inputs unmount when collapsed and all parameters freeze while running.
- Verdict/comparison strip remains visible in idle, running, success, and error states.
- Primary evidence grid is 2:1: equity/benchmark/drawdown on the left, validation gates on the right.
- The compact empty state preserves the evidence/gates relationship without an oversized empty chart or repeated metric dashes. Its five questions match the completed validation gate; unassessed is not a pass.
- Comparison tray follows the evidence grid.
- Diagnostic summaries show all groups as compact rows or accordions, with the most severe warning expanded.
- Recent runs show at most five rows in the first view.
- Editing parameters never relabels prior evidence as a new result. The previous run stays identified until a new run completes.

### 6.3 Alerts, `/alerts`

Reference: `proposed-alerts-native.png`.

- Decision strip summarizes pending review, affected holdings, candidates, and the loaded queue size. Only label events as today's changes if event timestamps support that claim; fetch time is not source freshness.
- Main triage grid is three columns at desktop widths from 1280 px upward: 184 px filter rail, flexible inbox, 400 px inspector.
- Left: queue categories plus severity, source, and relevance filters.
- Center: dense ranked alerts with age, source, evidence strength, affected exposure, and disposition.
- Show five rows per page and keep pagination outside the list scroller. Counts refer to the loaded response, not an implied complete database history. Search/filter changes reset the page; details belong to the current visible slice. Empty results clear the inspector.
- Right: selected alert evidence, portfolio impact, and state-changing actions.
- Resolve, snooze, or mark-reviewed is the primary action. Opening research context is secondary.
- API error remains inside the queue/data pane. Header, filters, inspector shell, retry, and audit ledger remain available.
- Audit entry stays visible and opens a bounded history region on demand. It represents the loaded records' latest states, not a complete immutable audit log.

### 6.4 Evolution Monitor, `/evolution`

Reference: `proposed-evolution-native.png`.

- Header shows freshness, evaluation health, compute budget, and pending proposal count.
- Decision strip states whether intervention is required.
- Primary grid is 2:1: OOS timeline left, selected-change evidence right.
- Promotion funnel is always visible and reports counts; dwell time is shown only when supported by real data.
- Pending proposals and change ledger are visible bottom panes. The ledger is not hidden behind a generic `<details>` element.
- “Review changes” remains the primary action. With zero proposals it may be disabled or explain that nothing awaits review, but it does not transform into an unrelated action.
- Partial endpoint failures identify the affected pane and preserve successfully loaded evidence.

### 6.5 Screener, `/screener`

The repository does not contain a canonical generated Screener reference image. Until one is approved, this route follows the decision-first structure shared by Today Recommendations and Paper Trading.

- Header exposes factor-library size, selection count, data date, and point-in-time membership status.
- Decision strip is the only home of the filled primary Run action. It summarizes selected factors, target count, eligible universe, and sector concentration.
- Setup uses a desktop workbench grid: bounded factor selection and combination controls on the left, universe and data date on the right. Do not stretch a short factor list to the full height of unrelated filters.
- Backend placeholder sectors such as `Unknown`, `Unclassified`, or blank values are not selectable filter options. Missing classification remains explicit in results.
- Chinese locale translates interface chrome and explanatory text. Conventional quant abbreviations may remain in English only when a hover and keyboard-focus definition is available.
- Results distinguish source-universe size, eligible count, eligibility rate, rank score, basket mean, and combination method. A score is never described as expected return.
- Factor selection shows five rows per page; results show ten. Search covers the full loaded factor library; CSV and aggregates retain the full result. Page changes close expanded row details. Sector translations change display only, never API or CSV values.

### 6.5a Report, `/report`

- The first screen is a report composer: name/expression and a single Generate action beside direction, neutralization, benchmark and cost. Historical examples and saved factors open in a searchable, five-row library dialog.
- Loading a source stages a draft. Only Generate computes evidence, except the existing explicit report-prefill handoff. Historical fixture returns are not this run's results.
- Completed reports lead with an evidence-based verdict, equity and run settings. Comparison and deep diagnostics open on demand; print retains the complete diagnostics.
- Name, expression, parameters and generation time belong to the completed snapshot. Edited drafts are marked unverified; comparison and export use the original report's settings, including the 70/30 train/test split and 30% sleeves.

Implementation and acceptance record: [2026-11-03 research workspace refinement](2026-11-03-research-workspaces-refinement.md).

### 6.6 Round-two recovery and density rules

- Alpha keeps the translated expression available for a parameter-only rerun. That action always uses the latest visible validation parameters.
- Backtest daily holdings are an explicit opt-in because they add roughly 200 KB to a response. Empty Holdings and Operations panes explain whether data was not requested or requested but unavailable, and state how to recover.
- Validation gates are decision questions, not five unrelated KPI thresholds: OOS performance, walk-forward stability, cost robustness, concentration, and point-in-time data risk.
- Pending proposal queues paginate at five rows and allow only one expanded proposal. Change-ledger previews remain bounded so the page does not grow in proportion to backlog size.

### 6.7 BRAIN Factor Mining, `/brain`

- A mining run is the primary navigation object. Candidate rows belong to one run and pagination must never split one run merely because newer runs inserted rows ahead of it.
- The run composer distinguishes simulation budget from generated candidates. The single filled primary action starts mining; refresh, stop tracking, and configuration recovery remain secondary.
- Reusing a run loads its family and budget into the composer but always creates a new child run. Historical evidence is never overwritten.
- Long-running status reports the real funnel separately: requested, generated, screened, simulated, persisted, and final outcome counts. A bypassed or partially parsed LLM screen is never labelled as a successful screen.
- Recent runs use a bounded selector and preserve manual, scheduled, and legacy provenance. Returning to the page restores the active or selected run without changing its candidate count.
- The selected-run workbench shows a compact outcome summary, then separates `Simulation Results` from `Candidate Audit`. Simulated rows and unsimulated generated candidates never share one ambiguous table.
- Every generated expression is written to a durable run-scoped candidate ledger before optional LLM screening. The audit view exposes settings, mechanism, evidence, LLM technical state, selection decision, and exact withholding reason; `brain_alphas` remains the official-simulation outcome table.
- Filters and pagination apply within the selected run only. A completed run with generated candidates but zero simulations opens the audit view by default and points users to the blocking evidence instead of showing an unexplained empty result table.
- Candidate detail keeps BRAIN-official metrics separate from Alpha Agent diagnostics, including adjusted self-correlation, lineage, retry history, and local screening evidence when available.
- Official self-correlation uses BRAIN's `0.70` hard limit. `0.65` to `0.70` is an internal warning band only: it may prompt a marginal-contribution review but must not reject an otherwise eligible alpha.
- A missing official self-correlation exposes its real state: pending computation, skipped because an earlier prerequisite failed, or temporarily unavailable after a bounded poll. GOOD-or-better rejected rows receive bounded post-run enrichment so useful research evidence is not silently discarded.
- Performance quality and novelty are separate verdict axes. A candidate may be high quality but redundant; the UI names both states and recommends switching mechanism or data rather than implying that a good grade guarantees submission eligibility.
- Options mining means multiple economic mechanisms, not one IV-skew template. The selected pool exposes mechanism labels and uses a bounded diversity quota before real simulations.
- The simulation budget is a ceiling. Options candidates are ranked by economic logic, official field coverage and mapping, historical mechanism outcomes, concentration risk, outcome alignment, structural complexity, and behavioral novelty. Weak candidates are withheld instead of backfilled merely to spend the budget.
- A mechanism label is not proof of diversity. PCR-gated call-minus-put variants share one behavioral cluster, while new legs must be tested independently or residualized against the dominant anchor before they receive a discovery slot.
- Expanded options rows expose a durable research-evidence card: source hypothesis, target outcome, official field mapping, coverage, context sample size, falsification rule, and any validated proxy estimates. A paper citation never substitutes for a faithful field mapping.
- Field ID coverage and semantic fidelity are separate. Official name and description evidence must identify measure type, call/put side, tenor or moneyness, and target alignment; a high-confidence claim with missing required semantics is withheld rather than relabelled as validated.
- Paired option legs use shared official tenor or moneyness when available. A live-catalog call leg is never silently paired with an unrelated static put fallback, and ordinary put-call open interest is never described as buyer-initiated opening flow.
- A cheap proxy may affect at most 15% of pre-screen ranking and only after chronological holdout validation beats an intercept baseline. Insufficient or rejected models fall back to the hierarchical posterior. `1 − adjusted self-correlation²` is labelled a diversification proxy, never a measured portfolio marginal return.
- A validated proxy predicts only inside observed feature and `mechanism × dataset × settings` support. Chronological drift or unseen contexts deactivate the prediction instead of extrapolating confidence.
- Empty and failed runs explain the failing stage and recovery action. A completed run with fewer persisted candidates than requested exposes the stage where the count changed.
- LLM timeout, provider failure, partial parsing, deterministic fallback, and low candidate evidence are distinct states. A technical screening failure must not be presented as poor BRAIN backtest quality, and old runs without candidate-ledger rows must say that their per-expression evidence is not recoverable.
- Kimi logic screening uses one latency-aware full-pool call so the reasoning startup cost is paid once. The call has a 240-second outer boundary below the client read timeout and is never synchronously retried. Partial usable scores remain valid; unscored candidates still enter the shared deterministic evidence screen. The UI reports call mode, elapsed time, scored, evidence-selected, and BRAIN-simulated counts separately, while remaining backward-compatible with historical batch telemetry.
- Completed runs expose screen utilization, pass yield, simulation-error rate, and one evidence-based next action. Recommendations remain advisory and never auto-submit an alpha.

### 6.8 Today Recommendations, `/picks`

- Per-ticker “1-day direction agreement” is a descriptive next-trading-day outcome check. It is never labelled generic hit rate, confidence, or predictive skill, and every trailing window carries its realized sample count.
- Tactical `confidence` is explicitly a 5-trading-day calibrated output. Strategic 60-day mode does not reuse that calibration and keeps confidence unavailable until its own forward evidence exists.
- Medium-horizon evidence uses the fixed 5, 20, and 60 trading-day composite-ranked baskets. Every horizon shows long-sleeve return, short-sleeve return, long-short spread, rank-IC, and usable-date count in parallel; the UI does not select a flattering horizon after observing results.
- The 1-day archived Top/Bottom basket check is secondary and keeps long, short, market, spread, cost, turnover, and SPY evidence separate. A long-short spread is not described as market-beta neutral without an explicit beta hedge.
- The compatibility API may retain historical baseline fields, but the approved interface does not present an always-up baseline. Metric labels and tooltips must still make object, horizon, direction, and sample scope explicit.

## 7. Interaction and accessibility

- Keyboard focus must be visible on every control.
- Tables and queues require semantic headings and a readable selected state.
- Color is never the only carrier of severity or pass/fail status.
- Destructive or state-changing actions state their effect and support recovery where the backend permits it.
- Skeletons appear when work exceeds roughly 300 ms. No infinite spinners without status copy.
- Charts provide text summaries and stable empty/error geometry.

## 8. Cross-cutting conventions audit

Before merging any of the four pages, check:

- The same metric name, threshold color, freshness phrase, and state label mean the same thing across pages.
- The only filled green action is the page’s primary action.
- Empty, loading, stale, unauthorized, partial, and failed states use the same pane-state grammar.
- User actions are distinguishable from system observations in the ledger.
- Research results are traceable to input parameters, data freshness, and a run or event identifier where available.
- Dense desktop layout does not create horizontal overflow at 1440 × 900 or 1672 × 941.

## 9. Principles re-check

1. Status is exposed in the header and affected pane.
2. Cognitive load is reduced by a stable decision-first order.
3. Recovery is local to the failed pane and includes retry when meaningful.
4. Defaults are explicit and not presented as validated facts.
5. Each screen has one primary action.
6. Evidence and counter-evidence are adjacent to the decision.
7. History remains visible and auditable.
8. Real data semantics outrank visual resemblance.
9. Controls preserve keyboard and screen-reader access.
10. Desktop density is intentional, with compact rows and limited decoration.
11. Cross-page terminology and status colors remain consistent.

## 10. Visual acceptance

For in-place refinement, capture the actual before/after page at the same desktop dimensions, locale, theme, data and interaction state. Generated-reference geometry targets below apply only to an explicitly requested reference reproduction, not to every small refinement. Acceptance requires:

- page sections appear in the same order;
- primary grid ratios differ by no more than 5 percentage points;
- first-fold vertical boundaries differ by no more than 24 px where content state is comparable;
- the primary action, decision strip, evidence inspector, and ledger are all visible or structurally preserved;
- no horizontal overflow, clipped labels, hydration errors, or page-level error replacement;
- live data and state transitions still pass focused tests and production-path checks before deployment.

### 10.1 Bounded-workspace review pass

This extends the existing acceptance contract, not a second design system. The
[session error-analysis catalog](2026-11-03-frontend-error-analysis.md) records
the user corrections, verified causes and remaining evidence limits.

1. Name the keep/refine/replace boundary. Existing-product refinement does not authorize new branding, navigation or a new page archetype.
2. Inspect first page, another page, last page, empty filter and one selected detail with realistic content. Verify root/main/local scroll ownership and bottom boundary, not only the first screenshot. Preserve total counts and access to all loaded items.
   For side-by-side panes and tile grids, inspect both the longest individual disclosure and the combined permitted expanded state in the whole viewport. Check the adjacent pane and the next section, not only whether the clicked control opened. A variable-length evidence list must not set an unrelated pane's height: move it into a full-width evidence region, paginate it, or use the existing dialog/drawer. `items-start` alone only removes stretched paint; it does not remove the grid row's empty space. Record behavioral and composition acceptance separately.
3. Use hover for short definitions, dialog/drawer for extended evidence. Missing data and next recovery action remain discoverable without reading a giant tooltip. Controls and long labels must fit both locales.
4. Preserve selection, focus, parameters and entity context across transitions. For this workstation, page changes use short opacity-only transitions with reduced-motion support, no positional entry or animated numeric values.
5. Validate actual state semantics: source versus fetch time, not requested versus unavailable, no result versus zero, loaded subset versus full history. Do not mask gaps to make a screenshot look finished.
6. Report implementation, browser verification, user visual acceptance and production release separately. After authorized release, inspect the two affected production paths; reuse focused checks instead of repeating full audits or expanding to unrelated modules.

Future incidents of these same families extend the linked catalog. Do not add
duplicate always-loaded AGENTS rules or new skills for each instance.

### 10.2 Advanced research refinement, 2026-11-03

- Zoo opens on the local factor catalog. Search, direction/status filters, saved-metric sorting and 5/10-row pagination share the existing table and field grammar. Long expressions open in a dialog; deletion requires confirmation and reports storage failure. Curated historical examples are labeled, not presented as current backtests or server-synchronized assets. Distribution/ranking charts need at least 10 recorded samples; smaller libraries retain explicit summary values without duplicated top/bottom lists. Correlation remains a separate on-demand calculation, capped at 20 most recently saved factors and disclosing its uniform long/short convention.
- Evolution separates methodology-factor and strategy-parameter reviews. The header counts both loaded queues; failed requests remain unknown rather than zero. Missing IC observations use compact explanatory panes. Weight-state totals may overlap, and ledger promotions are historical events, not a conversion funnel. Review and history lists use five-row pages; diagnostics and secondary history remain discoverable disclosures.
- BRAIN separates the new-run composer from the selected-run review. Family/grade/status labels are localized without changing API values. Successful LLM diagnostics are not rendered as warnings. Results default to ten rows with one expanded result; candidate audit also defaults to ten rows and discloses partial loading. Filtering and page changes reset incompatible detail state. Official submission acceptance is based on the response and stored BRAIN status, not merely a timestamp; HTTP success does not imply acceptance or ACTIVE status.
- No new motion library, chart package, production polling, mining calls or database changes are introduced. The keep/refine/replace boundary and evidence limits are recorded in `2026-11-03-advanced-research-refinement.md`.

### 10.3 Reference workspace refinement, 2026-11-03

- Guide keeps its six chapters, with a bounded topic index and a single article. Global bilingual search includes steps; clearing it restores the pre-search topic. The displayed content version is not a live-service guarantee.
- Data separates coverage, roster, sources and expression catalog requests. Failure in one pane must not erase another successful result. Roster and catalogs are searchable/paginated, with total loaded counts. Close coverage means non-null close cells, not cache efficiency or real-time freshness; declared cadence is distinct from observed timestamps.
- Coverage overview and roster keep their compact two-column comparison. Variable-length field evidence sits below both panes at full width; one coverage group opens at a time, with eight fields or six missing tickers per page. Expression catalog tiles open the shared dialog rather than stretching sibling tiles. Methodology pipeline sources sit in a full-width section before the short bias/sector pair.
- Methodology treats schemas and formulas as static definitions, distinct from measured panel coverage and callable operators. Ten-row directories expose formula/signature/source details on demand, with localized category and sector labels.
- Settings separates model connection, BRAIN, preferences, history and account data. Saved configuration and draft configuration must be visibly different. Encrypted storage is not a successful connectivity test. Unchanged saved credentials may be tested without re-entry; changed connection fields obey the existing API save contract. History and watchlist are bounded without discarding loaded items; destructive actions require explicit confirmation.
- Before/after evidence, scope and current production incident are recorded in `2026-11-03-reference-workspaces-refinement.md`.
