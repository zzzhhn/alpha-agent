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
| Form controls | Use the canonical TM field family, including `TmRange` and rich-option `TmSelectMenu`; do not add route-local native styling |
| Row actions | Use `TmRowButton` for a full interactive row and keep inline actions independently named |
| Overlays | Dialogs and drawers share `useTmModalFocus`; Escape closes and focus returns to the trigger |
| Charts | SVG and canvas colors resolve from shared semantic chart tokens; every chart retains a text summary |

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

For each route, capture a 1672 × 941 screenshot in dark Chinese locale and compare it to the native reference. Acceptance requires:

- page sections appear in the same order;
- primary grid ratios differ by no more than 5 percentage points;
- first-fold vertical boundaries differ by no more than 24 px where content state is comparable;
- the primary action, decision strip, evidence inspector, and ledger are all visible or structurally preserved;
- no horizontal overflow, clipped labels, hydration errors, or page-level error replacement;
- live data and state transitions still pass focused tests and production-path checks before deployment.
