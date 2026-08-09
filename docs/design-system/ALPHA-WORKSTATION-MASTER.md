# Alpha Workstation Master Design System

Status: implementation source of truth

Scope: desktop research workbenches at `/alpha`, `/backtest`, `/alerts`, and `/evolution`

Reference viewport: 1672 × 941 px

Reference images: `references/alpha-workbench/proposed-*-native.png`

## 1. Product contract

AlphaCore is a decision workstation, not a generic dashboard. Each screen must let a researcher answer, in order:

1. What changed or what am I testing?
2. Is the evidence sufficient to act?
3. What is the one primary action?
4. What evidence, risk, and history support that action?

The generated reference images define desktop geometry and information hierarchy. Live implementation must preserve real API data and honest empty, loading, stale, and error states. It must never invent a successful result merely to resemble a populated reference.

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
| Row density | 32 to 44 px for queues, tables, and ledgers |
| Primary action | One filled `--tm-accent` action per screen |
| Secondary actions | Outline or text actions; refresh must not compete with the primary action |

## 4. Typography and tokens

- Product and page titles use the current display serif treatment.
- Labels, controls, status, tables, formulas, and numeric values use `font-tm-mono` or `font-mono`.
- Labels are 9 to 11 px with controlled letter spacing. Body copy is 11 to 13 px. Page titles are 27 to 31 px.
- Use the existing tokens in `frontend/src/app/globals.css`: `--tm-bg`, `--tm-bg-2`, `--tm-bg-3`, `--tm-fg`, `--tm-fg-2`, `--tm-muted`, `--tm-rule`, `--tm-rule-2`, `--tm-accent`, `--tm-warn`, `--tm-neg`, and `--tm-info`.
- Green means healthy, validated, or primary action. Amber means incomplete or requires review. Red means failed or blocked. Muted text must remain readable on `--tm-bg`.

## 5. Shared composition

Every page follows this order:

1. `WorkbenchHeader`: page identity plus freshness, engine health, or run context.
2. Input or decision context strip.
3. `DecisionStrip`: current verdict and the minimum decisive metrics.
4. Primary workbench: the largest evidence view plus a contextual inspector.
5. Comparison, funnel, or diagnostic summaries.
6. Visible decision ledger.

Async panes keep their geometry in all states. Loading uses a skeleton inside the pane. Empty explains the next action. Error contains the error and retry in the affected pane. A single failed request must not erase unrelated controls, queue navigation, or history.

## 6. Page geometry

### 6.1 Factor Alpha, `/alpha`

Reference: `proposed-factors-native.png`.

- Header: research stage, universe, and truthful data/engine state.
- Hypothesis composer: wide thesis field with compact validation controls and one green “translate and backtest” action.
- Verdict: four equal metrics for IC, Sharpe, drawdown, and evidence completeness.
- Evidence row: three equal columns for expression/data lineage, IS/OOS validation, and falsification/risk gates.
- Ledger: visible dense recent-experiments table at the bottom of the first workbench flow.
- Required provenance indicators: input fields, lookback, lag/PIT status when returned by the service. Never fabricate PIT compliance.

### 6.2 Backtest, `/backtest`

Reference: `proposed-backtest-native.png`.

- Setup strip remains compact and does not consume the whole first fold.
- Verdict/comparison strip remains visible in idle, running, success, and error states.
- Primary evidence grid is 2:1: equity/benchmark/drawdown on the left, validation gates on the right.
- The empty state preserves this 2:1 shell with chart axes, validation rows, and next-step copy instead of a large blank panel.
- Comparison tray follows the evidence grid.
- Diagnostic summaries show all groups as compact rows or accordions, with the most severe warning expanded.
- Recent runs show at most five rows in the first view.

### 6.3 Alerts, `/alerts`

Reference: `proposed-alerts-native.png`.

- Decision strip summarizes today’s change count, affected holdings, candidates, and queue size.
- Main triage grid is three columns at desktop widths from 1280 px upward, target ratio `0.9fr 2.2fr 1.25fr`.
- Left: queue categories plus severity, source, and relevance filters.
- Center: dense ranked alerts with age, source, evidence strength, affected exposure, and disposition.
- Right: selected alert evidence, portfolio impact, and state-changing actions.
- Resolve, snooze, or mark-reviewed is the primary action. Opening research context is secondary.
- API error remains inside the queue/data pane. Header, filters, inspector shell, retry, and audit ledger remain available.
- Audit ledger is visible and can expand beyond the latest three records.

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
- Setup uses a desktop workbench grid: factor selection on the left, universe and combination controls on the right.
- Backend placeholder sectors such as `Unknown`, `Unclassified`, or blank values are not selectable filter options. Missing classification remains explicit in results.
- Chinese locale translates interface chrome and explanatory text. Conventional quant abbreviations may remain in English only when a hover and keyboard-focus definition is available.
- Results distinguish source-universe size, eligible count, eligibility rate, rank score, basket mean, and combination method. A score is never described as expected return.

### 6.6 Round-two recovery and density rules

- Alpha keeps the translated expression available for a parameter-only rerun. That action always uses the latest visible validation parameters.
- Backtest daily holdings are an explicit opt-in because they add roughly 200 KB to a response. Empty Holdings and Operations panes explain whether data was not requested or requested but unavailable, and state how to recover.
- Validation gates are decision questions, not five unrelated KPI thresholds: OOS performance, walk-forward stability, cost robustness, concentration, and point-in-time data risk.
- Pending proposal queues paginate at five rows and allow only one expanded proposal. Change-ledger previews remain bounded so the page does not grow in proportion to backlog size.

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

For each route, capture a 1672 × 941 screenshot in dark Chinese locale and compare it to the native reference. Acceptance requires:

- page sections appear in the same order;
- primary grid ratios differ by no more than 5 percentage points;
- first-fold vertical boundaries differ by no more than 24 px where content state is comparable;
- the primary action, decision strip, evidence inspector, and ledger are all visible or structurally preserved;
- no horizontal overflow, clipped labels, hydration errors, or page-level error replacement;
- live data and state transitions still pass focused tests and production-path checks before deployment.
