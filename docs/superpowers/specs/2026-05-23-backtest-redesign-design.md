# /backtest Redesign Design Spec

> **Status:** Brainstorm complete 2026-05-23. Awaiting user review before invoking writing-plans skill.

## 1. Goal

Redesign `/backtest` from a 1368-line, 14+ pane single-shot result viewer into a tuning-session-optimized workstation. Sticky-top form lets the user adjust 4 high-frequency params (expression + direction + top_pct + universe) and one click triggers a backtest; the verdict bar reports 5 metrics with delta-from-previous-run indicators; 3 default evidence panes (EQUITY + DRAWDOWN + WALKFORWARD) appear inline; 11 deeper analytical panes split into 4 collapsible groups (RISK + REGIME + HOLDINGS + OPERATIONS); a session-scoped RECENT RUNS table at the bottom lets the user re-fill, pin as baseline, or save to Zoo per row.

## 2. Non-goals

- Cross-device run history (RECENT RUNS is session-only; refresh clears it; Zoo persistence is the only cross-device anchor).
- Automatic parameter-sweep mode (user manually adjusts and re-runs; no "sweep top_pct from 10-50%" button in v1).
- Backend API changes (the existing `runFactorBacktest` endpoint stays; redesign is purely frontend orchestration).
- Migrating away from the existing 14 backend pane content; redesign rearranges + groups them, does NOT remove computed data fields.

## 3. Cross-cutting conventions audit (per `feedback_cross_cutting_conventions_audit`)

Audited BEFORE writing components to avoid the i18n/font drift that hit /alpha:

| Convention | Current state | Redesign must |
|------------|---------------|---------------|
| i18n keys (`backtest.*` namespace) | 276 existing zh+en keys (~138 unique) | REUSE existing keys for known strings (e.g. error prefix, label names); add new keys ONLY for redesign-specific wording (PIN AS BASELINE, delta indicators, group toggles). |
| Font convention | 18 `font-tm-mono` usages on the current page | Apply `font-tm-mono` to all redesigned headers/labels/body; `font-mono` only on numeric/code cells. |
| Layout wrappers | `<TmPane title=...>`, `<TmSubbar>`, `<TmStatusPill>` widely used | Redesigned components MUST reuse `TmPane` chrome for visual cohesion with /picks /alpha /evolution. |
| Locale-aware data | Form labels and pane titles route through `t(locale, "...")` today | Preserved; new components consume `useLocale` from the start. |
| Sidebar nav | `{ id: "backtest", href: "/backtest", labelKey: "lifecycle.backtest" }` exists | No change. The route stays at `/backtest`. |
| Loading skeleton | `loading.tsx` exists from Phase UX-0 | Keep; do NOT delete. |

## 4. Decisions locked (2026-05-23 brainstorm)

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | **Mode = tuning session** | The page exists to iteratively probe one factor's behavior across param choices, not to read a single report. The 14 analytical panes earn their place only if they remain reachable without dominating every run. |
| 2 | **Layout = sticky-top form + scrolling results** | `position: sticky` keeps the form available without scroll-back during tuning loops. Results scroll under it. Matches the existing single-column dashboard style. |
| 3 | **Verdict bar = 5 metrics + delta-from-previous + PIN AS BASELINE + SAVE TO ZOO** | Tuning hinges on knowing "is THIS run better than the LAST one." The 5 metrics (Sharpe / maxDD / IC / Turnover / AnnRet) cover return + risk + signal + cost + absolute. Delta arrows accelerate judgment. PIN AS BASELINE lets the user explicitly anchor the "vs prev" reference instead of defaulting to last-run. |
| 4 | **Default evidence panes = EQUITY + DRAWDOWN + WALKFORWARD** | EQUITY shows curve shape (smooth vs ragged); DRAWDOWN shows pain bands; WALKFORWARD shows IC consistency across folds (most diagnostic for tuning decisions). Risk attribution is interesting once per factor but boring after the 5th tuning run; moved to the RISK accordion. |
| 5 | **RECENT RUNS = session-only N=10 with per-row [refill, pin, zoo]; Zoo and Baseline are independent** | Persistence layers: Zoo = permanent cross-device favorites; Baseline = session-only tuning anchor; RECENT RUNS table = session-only history. Three orthogonal mechanisms; do NOT collapse them. |
| 6 | **11 hidden panes = 4 grouped accordions: RISK (3) + REGIME (2) + HOLDINGS (2) + OPERATIONS (2)** | Grouping by domain (rather than one giant "Show all 11" toggle) lets the user open exactly what they want to investigate without flooding the viewport. |
| 7 | **Auto-expand = badge-on-toggle, no auto-expand** | Tuning loops re-fire alerts every run; auto-expand would re-shuffle the layout each click. Badges on the closed toggle (e.g. "RISK ⚠ drawdown over threshold") preserve discoverability without flapping the page. |
| 8 | **Form = high-frequency 4 visible + Advanced 6 collapsed** | Visible: expression, direction, top_pct, universe (the 4 a tuning user touches every run). Advanced: bot_pct, lookback, benchmark, neutralize, transaction_cost_bps, mode (touched once per factor or session). |

## 5. Architecture

```
[Sticky top, persistent across scroll]
+--------------------------------------------------+
| EXPRESSION  <textarea, 1 line + grow-on-focus>   |
| dir [v] top [%] universe [v]   [+] Advanced  [RUN BACKTEST] |
+--------------------------------------------------+

[Scrolls under sticky top]
+--------------------------------------------------+
| VERDICT BAR                                      |
|  Sharpe  ✓ ↑+0.10 | maxDD  ⚠ ↑-3% | IC  ✓ →+0.005 | Turn ✓ ↓-8% | AnnRet ✓ ↑+2% |
|  [SAVE TO ZOO]  [PIN AS BASELINE]                |
+--------------------------------------------------+
| EQUITY     | DRAWDOWN  | WALKFORWARD             |
+--------------------------------------------------+
| [+] RISK DETAIL (3 panes) [⚠ if maxDD/winrate flagged] |
| [+] REGIME BREAKDOWN (2 panes)                   |
| [+] HOLDINGS (2 panes)                           |
| [+] OPERATIONS (2 panes) [⚠ if turnover flagged] |
+--------------------------------------------------+
| RECENT RUNS                                       |
|  Run  Sharpe  maxDD  IC     Turn   AnnRet  params  actions    |
|  10   1.23 ↑  -12% ↑  0.034  28%   18%    top=30  [re|pin|zoo]|
|  9 ★  0.98    -18%   0.029  35%   12%    top=20  [re|pin|zoo]|
|  ...                                              |
+--------------------------------------------------+
  ★ = current baseline (the ↑/↓ deltas above are computed vs THIS row)
  empty 11th row triggers "Run a backtest above to start" placeholder
```

A `useBacktestSession` hook owns: form state, current run state, recent runs array (capped at 10), pinned baseline run id. The verdict bar derives delta vs the baseline (or vs the previous run if no baseline pinned). Each group accordion has independent open/closed state + a badge derived from the current run's metrics crossing thresholds.

## 6. State machine

```
SessionState
  ├─ formState: { expression, direction, topPct, bottomPct, universe,
  │                lookback, benchmark, neutralize, transactionCostBps, mode,
  │                advancedOpen: bool }
  ├─ runState:
  │    ├─ idle
  │    ├─ running
  │    ├─ ok       (carries FactorBacktestResponse)
  │    └─ error    (carries message string)
  ├─ recentRuns: Run[]   (capped at 10; FIFO; session-only)
  └─ baselineRunId: string | null    (the ★ row; deltas compute vs this)

Run = {
  id: string,
  ts: epoch_ms,
  params: BacktestParams,    // snapshot of formState at submit time
  metrics: { sharpe, maxDD, ic, turnover, annReturn },
  raw: FactorBacktestResponse,
}

VerdictBar derives delta from:
  baselineRunId ? recentRuns.find(r => r.id === baselineRunId)
                : recentRuns[recentRuns.length - 2]  // previous run

Group accordion badges derive from current-run thresholds:
  RISK badge ⚠ if maxDD < -25% OR winRate < 0.4
  OPERATIONS badge ⚠ if turnover > 0.6
  (REGIME, HOLDINGS have no auto-badge in v1)
```

## 7. Component tree

```
<BacktestPage>
  <BacktestFormSticky>
    <ExpressionField />
    <QuickParamsRow />     // direction / top_pct / universe
    <AdvancedParamsCollapsible />  // 6 params + RUN button
  </BacktestFormSticky>

  <BacktestVerdictBar>
    <MetricsRow />         // 5 metrics with delta arrows
    <ActionsRow />         // SAVE TO ZOO + PIN AS BASELINE
  </BacktestVerdictBar>

  <BacktestEvidenceGrid>
    <EquityCurvePane />
    <DrawdownPane />
    <WalkforwardPane />
  </BacktestEvidenceGrid>

  <BacktestAnalyticsGroups>
    <GroupAccordion title="RISK DETAIL" badge={...}>
      <RiskAttributionPane />
      <WorstDrawdownsPane />
      <WinLossDistributionPane />
    </GroupAccordion>
    <GroupAccordion title="REGIME BREAKDOWN">
      <TrainTestSplitPane />
      <RegimeBreakdownPane />
    </GroupAccordion>
    <GroupAccordion title="HOLDINGS">
      <PortfolioTodayPane />
      <PositionContributionPane />
    </GroupAccordion>
    <GroupAccordion title="OPERATIONS" badge={...}>
      <TurnoverProfilePane />
      <DailyBreakdownPane />
    </GroupAccordion>
  </BacktestAnalyticsGroups>

  <RecentRunsTable>
    // 10-row table; per-row actions [refill | pin | zoo]
  </RecentRunsTable>
</BacktestPage>
```

## 8. Detailed section specs

### 8.1 BacktestFormSticky

A `<section className="sticky top-0 z-30 ...">` wrapping the 3 form rows.

- **ExpressionField**: full-width `<textarea>` collapsed to 1 row; expands to 3-4 rows when focused (`focus:rows-4`). Receives prefill from /alpha "Run Backtest" link OR /factors Zoo entry via the existing PrefillPayload mechanism (preserve verbatim).
- **QuickParamsRow**: 3 fields inline: direction select, top_pct number input (with `%` suffix), universe select. Width budget: ~80% of container; remaining 20% holds the "[+] Advanced" toggle.
- **AdvancedParamsCollapsible**: starts closed; click expands to reveal 6 more fields (bot_pct, lookback days, benchmark text, neutralize toggle, transaction_cost_bps, mode select). "RUN BACKTEST" button always at right end (visible whether Advanced is open or closed).

Sticky height: ~80px collapsed, ~140px expanded. CSS uses `transition: max-height` for smooth expansion.

### 8.2 BacktestVerdictBar

| State | Render |
|-------|--------|
| `runState.kind === "idle"` | Muted placeholder: "Run a backtest to see results." |
| `running` | Spinner + "Running... (ETA varies by universe and walk_forward depth)" |
| `error` | Red bar with message + Re-run button |
| `ok` AND recentRuns.length <= 1 | 5 metrics + traffic-light marks, no delta arrows |
| `ok` AND recentRuns.length >= 2 | 5 metrics + traffic-light + delta arrows (↑/↓/→) computed vs baselineRunId OR previous run |

Each metric span has a `title` tooltip with the threshold reasoning (matching /alpha pattern: "threshold >=1.0 considered viable"). Delta arrow is ↑ when "better" (Sharpe up, maxDD up toward 0, IC up, Turnover DOWN, AnnRet up), ↓ when "worse", → when |delta| < epsilon.

`[SAVE TO ZOO]` writes the current spec + metrics to localStorage Zoo and fires `toast.success("Saved to Zoo", { action: { label: "Undo", onClick: removeFromZoo } })`.

`[PIN AS BASELINE]` sets `baselineRunId = currentRun.id`. The pinned row in RECENT RUNS gets a ★ marker. Clicking PIN AS BASELINE when the current run is already pinned acts as an unpin (clears `baselineRunId`).

Thresholds (locked):
| Metric | ✓ | ⚠ | ✗ |
|--------|---|---|---|
| Sharpe | ≥ 1.0 | 0.5 to 1.0 | < 0.5 |
| maxDD | ≥ -15% | -25% to -15% | < -25% |
| IC | ≥ 0.02 | 0 to 0.02 | < 0 |
| Turnover | ≤ 0.4 | 0.4 to 0.6 | > 0.6 (lower = better) |
| AnnRet | ≥ 0.10 | 0 to 0.10 | < 0 |

### 8.3 BacktestEvidenceGrid

Three side-by-side panes on `lg:`, stacked on `sm:`. Each is a `TmPane`:
- **EquityCurvePane**: line chart of equity over time, benchmark overlay. Tooltip on hover shows date + value.
- **DrawdownPane**: filled area chart of drawdown series (always <= 0). Worst drawdown date + magnitude annotated inline.
- **WalkforwardPane**: bar chart of per-fold IC values. Optionally overlay a horizontal line at IC=0.02 threshold.

Each pane has the 4-state pattern from /alpha (waiting / loading / ok / error). The `loading` state uses `animate-pulse` blocks matching the chart silhouette.

### 8.4 BacktestAnalyticsGroups

Four GroupAccordion sections. Each `GroupAccordion`:
- Header: title + count `(N panes)` + optional `⚠` badge with reason text on hover.
- Click toggles open/closed.
- Closed = compact 1-line summary header.
- Open = stacked sub-panes inside the accordion body.

Badge logic:
- RISK badge ⚠ when `currentRun.metrics.maxDD < -25%` OR `currentRun.raw.win_rate < 0.4`.
- OPERATIONS badge ⚠ when `currentRun.metrics.turnover > 0.6`.
- REGIME and HOLDINGS have no badge logic in v1 (could add later if regime IC variance crosses a threshold).

Each sub-pane is the existing pane content from the current page.tsx (read its render path; the content is fine, only the wrapping changes).

### 8.5 RecentRunsTable

A `<table>` rendered inside a `TmPane` at the bottom of the page.

| Column | Width | Format |
|--------|-------|--------|
| Run # | 6ch | descending integer (10, 9, 8, ...) |
| ★ baseline marker | 2ch | ★ or empty |
| Sharpe | 8ch | 2-decimal + traffic-light glyph |
| maxDD | 8ch | percent + glyph |
| IC | 8ch | 4-decimal + glyph |
| Turnover | 6ch | percent |
| AnnRet | 6ch | percent |
| params summary | flex | "top=30% dir=LS univ=SP500" condensed |
| actions | 12ch | 3 icon buttons: `↻` refill / `★` pin (toggle) / `+` zoo |

Cap at 10 rows; older runs FIFO-evict. Newest at top. Empty state: "Run a backtest above to see history."

`refill` action: copies that row's params into the sticky form (does NOT auto-run).
`pin` action: sets `baselineRunId` to that row (or clears if already pinned).
`zoo` action: writes that row's spec + metrics to localStorage Zoo + toast.success with Undo (same flow as VerdictBar's SAVE TO ZOO).

### 8.6 Error UX

- **Translate-not-applicable**: this page does NOT call translate; it consumes a pre-formed expression. If the expression is malformed, the backend returns a 400/500 with a parse error; the verdict bar shows the error + Re-run button.
- **Backtest API failure**: same; verdict bar red + retry.
- **Toast on success/failure**: `toast.success("Backtest complete")` on `ok`, `toast.error("Backtest failed: ${msg}")` on `error`. The toast complements the verdict bar; the user can see status from either.
- **Locale switching mid-run**: form state survives (TypeScript state stays); only display strings change.

## 9. Migration strategy

Current `/backtest/page.tsx` is 1368 lines. Redesign cuts to ~150 lines + ~9 new component files:
- 1 hook (`useBacktestSession.ts`) ~120 lines
- 1 form section (`BacktestFormSticky.tsx`) ~140 lines
- 1 verdict bar (`BacktestVerdictBar.tsx`) ~110 lines
- 1 evidence grid (`BacktestEvidenceGrid.tsx`) + 3 evidence panes ~180 lines combined
- 1 analytics groups container + 4 accordions + 9 sub-pane wrappers ~280 lines combined (each sub-pane is a thin adapter over the existing pane content)
- 1 recent runs table (`RecentRunsTable.tsx`) ~120 lines
- types.ts ~40 lines

Estimated total: page.tsx ~150 + components ~990 = ~1140 lines (down from 1368 monolith), with much better separation. Old pane content is REPRESERVED INSIDE the sub-pane wrappers (do not lose the chart logic, just wrap it).

## 10. UX principles re-check

| # | Principle | How the redesign addresses it |
|---|-----------|-------------------------------|
| 1 | Intent alignment | Sticky form anticipates "user wants to change params next"; verdict delta arrows anticipate "user wants to know if this change helped." |
| 2 | Cognitive load minimization | 4 visible form fields + 5 metrics + 3 evidence panes = 12 high-attention slots above the fold. 11 deeper panes hidden in 4 groups. Recent runs table is a low-attention scroll-target. |
| 3 | Visibility of system status | Toast on every run; spinner + ETA inside verdict bar; delta arrows narrate "vs baseline"; baseline marker (★) on the pinned row. |
| 4 | Forgiveness | Re-run, refill from history, undo via toast all reversible. PIN AS BASELINE is one click toggle (no modal). |
| 5 | Affordance | RUN BACKTEST is the dominant accent button; ↻/★/+ icon buttons on RECENT RUNS rows have clear hover hints; delta arrows directly indicate "better/worse" without text. |
| 6 | Design disappears | After use, the user remembers "I tuned the factor"; the 14-pane chrome fades. |
| 7 | No manual needed | The sticky form's 4 visible fields are the same conceptual params anyone running a backtest knows (direction, top%, universe). Advanced is opt-in. |
| 8 | Respects user time | One click per tuning iteration; no modal interrupts; results scroll under sticky form so no page resets. |
| 9 | No dark patterns | Threshold tooltips visible; delta arrows can be both ↑ (good) and ↓ (bad); no buried failure states. |
| 10 | One clear Primary Action | RUN BACKTEST is the only accent-colored button in the form; SAVE TO ZOO + PIN AS BASELINE are secondary; per-row actions in RECENT RUNS are tertiary icon buttons. |

## 11. Open implementation questions (resolve during plan-writing)

1. **`FactorBacktestResponse` field paths**: T1 of /alpha redesign caught that the real field path is `test_metrics.sharpe` not `metrics.sharpe`. Verify by re-reading the type before writing the verdict bar. Also confirm `turnover` and `annualized_return` exist (the spec assumes they do).
2. **WALKFORWARD pane data source**: the existing page may compute walkforward fold IC inline from `daily_breakdown` or it may be a dedicated field on the response. Grep before the WalkforwardPane implementation.
3. **PrefillPayload mechanism**: the current page accepts a `prefill: PrefillPayload | null` state from /alpha or /factors. Confirm the mechanism + reuse verbatim in the new BacktestFormSticky.
4. **Existing pane content reuse**: each of the 9 sub-pane wrappers (under the 4 groups) is a thin adapter over current pane render code. During plan-writing, list each wrapper + the source line range in the current page.tsx to copy from.
5. **Toast on success duration**: /alpha's toast.success auto-dismisses; for tuning where the user runs many backtests, a long toast might overlap with the next run's toast. Consider shorter duration (~2s) for tuning's success toasts to avoid stacking.

## 12. Out of scope (explicitly deferred)

- Parameter sweep automation ("run top_pct from 10 to 50 in steps of 5").
- Diff view between two pinned runs (only one baseline at a time in v1).
- Exporting RECENT RUNS to CSV.
- Backend-driven persistence of RECENT RUNS (always session-only in v1).
- Per-user threshold customization (locked thresholds for v1).
- Integration with /factor-lab approved expressions (only /alpha and /factors prefill in v1).

---

**Next step**: User reviews this spec. On approval, invoke `superpowers:writing-plans` to produce the implementation plan.
