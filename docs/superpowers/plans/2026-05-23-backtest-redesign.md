# /backtest Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the 1368-line `/backtest/page.tsx` monolith with a tuning-session-optimized workstation: sticky-top form + 5-metric verdict bar with delta-from-previous + 3 default evidence panes (EQUITY + DRAWDOWN + WALKFORWARD) + 4 grouped analytics accordions (RISK / REGIME / HOLDINGS / OPERATIONS, 9 sub-panes total) + session-only RECENT RUNS table with per-row [refill / pin / zoo] actions. Cross-cutting conventions preserved (276 existing `backtest.*` i18n keys reused; `font-tm-mono` workstation aesthetic; TmPane wrappers).

**Architecture:** A `useBacktestSession` hook owns form state + current run state + recent runs (capped at 10) + baseline run id. Verdict bar derives delta vs baseline (or last run if no baseline). Each group accordion has independent open/closed state + a badge derived from current-run thresholds (no auto-expand). Each sub-pane is a thin wrapper around existing pane render code from the current page (preserve chart logic; only rearrange).

**Tech Stack:** Next.js 14 App Router, TypeScript, Tailwind (`tm-*` tokens), lucide-react, Phase UX-0 `useToast`, existing recharts charts from the current /backtest. No new deps. Reuses existing `runFactorBacktest` API client + `FactorBacktestResponse` type + the existing PrefillPayload flow from /alpha and /factors.

**API shape verified (pre-flight grep, from /alpha redesign T1 discoveries):** `FactorBacktestResponse.test_metrics` is the metrics field (NOT `metrics`). Fields confirmed: `sharpe, total_return, ic_spearman, n_days, max_drawdown?, turnover?, hit_rate?, ic_std, icir, ic_t_stat, ic_pvalue, psr, lucky_max_sr`. `runFactorBacktest({ spec, direction?, ... })` request shape.

---

## Dependencies + grounding (read first during Task 1)

- Current `/backtest/page.tsx` (1368 lines) — the source of truth for every existing pane's content + chart code + i18n key usage. Read its section ranges progressively per the section breakdown in T5/T6 below.
- Phase UX-0: `frontend/src/components/ui/toast/` exports `useToast` with success / error / info / dismiss; success auto-dismisses, error is sticky by default.
- /alpha redesign components live at `frontend/src/components/alpha/`. Use them as STYLE precedent (the new /backtest components live at `frontend/src/components/backtest/` parallel). Specifically: `HypothesisInputCard.tsx`, `VerdictBar.tsx`, `EvidencePaneGrid.tsx`, and `AnalyticsAccordion.tsx` show the patterns to mirror (without copy-pasting).
- Tokens (verified Phase UX-0): `tm-bg-2`, `tm-bg-3`, `tm-rule`, `tm-fg`, `tm-fg-2`, `tm-muted`, `tm-accent`, `tm-pos`, `tm-warn`, `tm-neg`, `tm-info`. NO `tm-card` / `tm-line` / `tm-fg-1`.
- i18n: `useLocale` from `@/components/layout/LocaleProvider`; `t(locale, "backtest.someKey" as Parameters<typeof t>[1])`. The 276 existing `backtest.*` keys cover most labels; new keys only for new redesign-specific copy (PIN AS BASELINE, delta indicators, group toggle labels, RECENT RUNS column headers).
- Font: `font-tm-mono` on body / headers / labels / button text; `font-mono` on numeric cells + code blocks.
- Layout wrappers: every section is a `<TmPane title=...>`. The existing /backtest uses TmPane extensively; preserve.

**Anti-pattern guardrails (lessons compounded):**
- Silent exception: every try/catch surfaces via toast OR pane error state. No `console.error`-only.
- Token correctness: only verified `tm-*` tokens; Tailwind silent-drops unknown classes.
- Grep call chain: before any field access on `FactorBacktestResponse`, confirm the path from `frontend/src/lib/types.ts`. The /alpha T1 implementer caught `test_metrics.sharpe` vs `metrics.sharpe`; the same lesson applies here.
- Cross-cutting conventions audit: every visible string MUST resolve through `t(locale, ...)`. Every body/label uses `font-tm-mono`.

---

## File Structure

- `frontend/src/components/backtest/types.ts` (new): SessionState, RunState, Run, ParamSnapshot, MetricsDelta, etc.
- `frontend/src/components/backtest/useBacktestSession.ts` (new): session hook.
- `frontend/src/components/backtest/BacktestFormSticky.tsx` (new): sticky form (expression + 4 visible + Advanced 6).
- `frontend/src/components/backtest/BacktestVerdictBar.tsx` (new): 5 metrics + delta arrows + actions.
- `frontend/src/components/backtest/BacktestEvidenceGrid.tsx` (new) + sub-files `EquityCurvePane.tsx` / `DrawdownPane.tsx` / `WalkforwardPane.tsx`.
- `frontend/src/components/backtest/BacktestAnalyticsGroups.tsx` (new) + 4 group accordions + 9 sub-pane wrappers.
- `frontend/src/components/backtest/RecentRunsTable.tsx` (new).
- `frontend/src/app/(dashboard)/backtest/page.tsx` (rewrite from 1368 -> ~150 lines).
- `frontend/src/lib/i18n.ts` (modify): add new `backtest.*` keys for redesign-specific copy.

Existing files NOT touched: `frontend/src/lib/api.ts`, `frontend/src/lib/types.ts`, `(dashboard)/backtest/loading.tsx`.

---

### Task 1: types + useBacktestSession hook

**Files:**
- Create: `frontend/src/components/backtest/types.ts`
- Create: `frontend/src/components/backtest/useBacktestSession.ts`

Pure-logic task; no UI; tsc-driven verification.

- [ ] **Step 1: READ the real shapes first**

```bash
grep -nA20 "interface FactorBacktestResponse\|interface FactorSplitMetrics\|interface FactorBacktestRequest" frontend/src/lib/types.ts
grep -nA10 "export const runFactorBacktest\|export async function runFactorBacktest" frontend/src/lib/api.ts
sed -n '90,135p' "frontend/src/app/(dashboard)/backtest/page.tsx"   # the existing form state shape
```

Record:
- The exact `FactorBacktestRequest` request shape (what the spec says: `{spec, direction?, ...}`; verify).
- The exact `FactorSplitMetrics` fields (sharpe, max_drawdown?, turnover?, etc.).
- The existing form state names + universe list.

- [ ] **Step 2: Implement `types.ts`**

```typescript
import type { FactorBacktestResponse, FactorSpec, FactorUniverse } from "@/lib/types";

export type RunState =
  | { kind: "idle" }
  | { kind: "running" }
  | { kind: "ok"; result: FactorBacktestResponse }
  | { kind: "error"; message: string };

export type DirectionMode = "long_short" | "long_only" | "short_only";
export type BacktestMode = "static" | "walk_forward";

export interface BacktestParams {
  expression: string;
  direction: DirectionMode;
  topPct: number;       // 0 to 100
  bottomPct: number;
  universe: FactorUniverse;
  lookback: number;     // days
  benchmark: string;    // ticker (e.g. "SPY")
  neutralize: boolean;
  transactionCostBps: number;
  mode: BacktestMode;
}

export interface RunMetrics {
  sharpe: number | null;
  maxDD: number | null;        // -0.15 means -15%
  ic: number | null;
  turnover: number | null;     // 0.28 means 28%
  annReturn: number | null;
}

export interface Run {
  id: string;
  ts: number;
  params: BacktestParams;
  metrics: RunMetrics;
  raw: FactorBacktestResponse;
}

export type MetricDirection = "up_good" | "down_good";   // Sharpe up_good; Turnover down_good
export type DeltaArrow = "up" | "down" | "flat";

export interface MetricDelta {
  arrow: DeltaArrow;
  diff: number;        // raw signed difference
  betterThanBaseline: boolean;
}
```

- [ ] **Step 3: Implement `useBacktestSession.ts`**

```typescript
"use client";

import { useCallback, useMemo, useState } from "react";
import { runFactorBacktest } from "@/lib/api";
import type {
  BacktestParams, MetricDelta, RunMetrics, RunState, Run,
} from "./types";

const MAX_RECENT_RUNS = 10;

// Thresholds (locked per spec §8.2)
const TH_SHARPE_OK = 1.0;
const TH_SHARPE_WARN = 0.5;
const TH_MAXDD_OK = -0.15;
const TH_MAXDD_BAD = -0.25;
const TH_IC_OK = 0.02;
const TH_TURNOVER_OK = 0.4;
const TH_TURNOVER_BAD = 0.6;
const TH_ANNRET_OK = 0.10;

function extractMetrics(raw: import("@/lib/types").FactorBacktestResponse): RunMetrics {
  const m = raw.test_metrics;
  return {
    sharpe: m?.sharpe ?? null,
    maxDD: m?.max_drawdown ?? null,
    ic: m?.ic_spearman ?? null,
    turnover: m?.turnover ?? null,
    // annualized_return likely computed from total_return + n_days:
    annReturn: m?.total_return != null && m?.n_days != null
      ? Math.pow(1 + m.total_return, 252 / m.n_days) - 1
      : null,
  };
}

function makeId(): string {
  return `run_${Date.now()}_${Math.floor(Math.random() * 1000)}`;
}

export function useBacktestSession() {
  const [params, setParams] = useState<BacktestParams>({
    expression: "",
    direction: "long_short",
    topPct: 30,
    bottomPct: 30,
    universe: "SP500",
    lookback: 252,
    benchmark: "SPY",
    neutralize: false,
    transactionCostBps: 10,
    mode: "static",
  });
  const [runState, setRunState] = useState<RunState>({ kind: "idle" });
  const [recentRuns, setRecentRuns] = useState<Run[]>([]);
  const [baselineRunId, setBaselineRunId] = useState<string | null>(null);

  const runOnce = useCallback(async () => {
    setRunState({ kind: "running" });
    try {
      const result = await runFactorBacktest({
        // Adapt to real request shape; the spec implies the request needs
        // a constructed FactorSpec, not raw expression. Adapt during impl.
        ...(/* construct request from params */ {} as any),
      });
      const metrics = extractMetrics(result);
      const newRun: Run = {
        id: makeId(),
        ts: Date.now(),
        params,
        metrics,
        raw: result,
      };
      setRecentRuns(rs => {
        const updated = [newRun, ...rs];
        return updated.slice(0, MAX_RECENT_RUNS);
      });
      setRunState({ kind: "ok", result });
    } catch (e) {
      setRunState({
        kind: "error",
        message: e instanceof Error ? e.message : String(e),
      });
    }
  }, [params]);

  const refillFromRun = useCallback((runId: string) => {
    const r = recentRuns.find(r => r.id === runId);
    if (r) setParams(r.params);
  }, [recentRuns]);

  const togglePin = useCallback((runId: string) => {
    setBaselineRunId(prev => prev === runId ? null : runId);
  }, []);

  const currentRun = useMemo(
    () => runState.kind === "ok" ? recentRuns[0] ?? null : null,
    [runState, recentRuns],
  );

  const baselineRun = useMemo(() => {
    if (baselineRunId) return recentRuns.find(r => r.id === baselineRunId) ?? null;
    return recentRuns[1] ?? null;
  }, [baselineRunId, recentRuns]);

  const computeDelta = useCallback((current: number | null, baseline: number | null, dir: "up_good" | "down_good"): MetricDelta | null => {
    if (current === null || baseline === null) return null;
    const diff = current - baseline;
    const EPS = 1e-4;
    const arrow = Math.abs(diff) < EPS ? "flat" : diff > 0 ? "up" : "down";
    const betterThanBaseline = dir === "up_good" ? diff > 0 : diff < 0;
    return { arrow, diff, betterThanBaseline };
  }, []);

  const deltas = useMemo(() => {
    if (!currentRun || !baselineRun || currentRun.id === baselineRun.id) {
      return { sharpe: null, maxDD: null, ic: null, turnover: null, annReturn: null };
    }
    return {
      sharpe: computeDelta(currentRun.metrics.sharpe, baselineRun.metrics.sharpe, "up_good"),
      maxDD: computeDelta(currentRun.metrics.maxDD, baselineRun.metrics.maxDD, "up_good"),  // closer to 0 = up = good
      ic: computeDelta(currentRun.metrics.ic, baselineRun.metrics.ic, "up_good"),
      turnover: computeDelta(currentRun.metrics.turnover, baselineRun.metrics.turnover, "down_good"),
      annReturn: computeDelta(currentRun.metrics.annReturn, baselineRun.metrics.annReturn, "up_good"),
    };
  }, [currentRun, baselineRun, computeDelta]);

  return {
    params, setParams,
    runState, runOnce,
    recentRuns, refillFromRun, togglePin,
    baselineRunId, currentRun, baselineRun,
    deltas,
    thresholds: {
      sharpe: TH_SHARPE_OK, sharpeWarn: TH_SHARPE_WARN,
      maxDD: TH_MAXDD_OK, maxDDBad: TH_MAXDD_BAD,
      ic: TH_IC_OK,
      turnover: TH_TURNOVER_OK, turnoverBad: TH_TURNOVER_BAD,
      annReturn: TH_ANNRET_OK,
    },
    isRunning: runState.kind === "running",
  };
}
```

The `runFactorBacktest` request construction must match the REAL API shape. The /alpha redesign T1 found it takes `{spec, direction?, ...}` where `spec` is a `FactorSpec` (not a raw expression string). Adapt accordingly during implementation.

- [ ] **Step 4: tsc clean**

`cd frontend && npx tsc --noEmit` → zero new errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/backtest/types.ts frontend/src/components/backtest/useBacktestSession.ts
git commit -m "feat(backtest): session hook + types for redesigned backtest page"
```

---

### Task 2: i18n keys for new redesign-specific copy

**Files:**
- Modify: `frontend/src/lib/i18n.ts`

276 existing `backtest.*` keys; add only the new ones the redesign needs.

- [ ] **Step 1: Audit existing keys**

`grep -nE 'backtest\\.' frontend/src/lib/i18n.ts | head -60`

Identify keys reusable for: error prefix, metric labels (Sharpe/IC/maxDD already covered), pane titles, form labels, button labels.

- [ ] **Step 2: Add new keys to both zh + en blocks**

Suggested additions (adapt to actual existing key conventions; reuse where possible):
```
"backtest.action.runBacktest"     // "RUN BACKTEST" / "运行回测"
"backtest.action.advancedShow"    // "+ Advanced" / "+ 高级"
"backtest.action.advancedHide"    // "Hide Advanced" / "收起高级"
"backtest.action.saveToZoo"       // "SAVE TO ZOO" / "保存到 Zoo"
"backtest.action.pinAsBaseline"   // "PIN AS BASELINE" / "钉为参照"
"backtest.action.unpin"           // "UNPIN" / "取消参照"
"backtest.action.refillFromRun"   // "Refill params" / "回填参数"

"backtest.verdict.idle"           // "Run a backtest to see results." / "运行回测后显示结果。"
"backtest.verdict.running"        // "Running... (ETA varies by universe and walk_forward depth)" / "回测中…（耗时随股票池和 walk_forward 深度变化）"
"backtest.verdict.errorPrefix"    // existing? grep first

"backtest.metric.sharpe"          // existing? grep first
"backtest.metric.maxDd"           // existing? grep first
"backtest.metric.ic"              // existing? grep first
"backtest.metric.turnover"        // existing? grep first; NEW if absent
"backtest.metric.annReturn"       // NEW
"backtest.metric.vsBaseline"      // "vs baseline" / "对比参照"
"backtest.metric.vsPrev"          // "vs prev run" / "对比上一次"

"backtest.evidence.equity"        // "EQUITY" / "净值曲线"
"backtest.evidence.drawdown"      // "DRAWDOWN" / "回撤"
"backtest.evidence.walkforward"   // "WALKFORWARD" / "Walk-forward IC"

"backtest.group.riskDetail"       // "RISK DETAIL" / "风险明细"
"backtest.group.regimeBreakdown"  // "REGIME BREAKDOWN" / "市场状态分解"
"backtest.group.holdings"         // "HOLDINGS" / "持仓"
"backtest.group.operations"       // "OPERATIONS" / "运营"
"backtest.group.showN"            // "Show {n} panes" / "显示 {n} 项"
"backtest.group.hideN"            // "Hide" / "隐藏"
"backtest.group.badgeDrawdown"    // "drawdown over threshold" / "回撤超阈"
"backtest.group.badgeWinRate"     // "low win rate" / "胜率偏低"
"backtest.group.badgeTurnover"    // "high turnover" / "换手过高"

"backtest.runs.title"             // "RECENT RUNS" / "近期运行"
"backtest.runs.empty"             // "Run a backtest above to see history." / "运行回测后这里会显示历史。"
"backtest.runs.colRun"            // "Run" / "运行"
"backtest.runs.colSharpe"         // existing? grep first
"backtest.runs.colMaxDD"          // existing? grep first
"backtest.runs.colIC"             // existing? grep first
"backtest.runs.colTurnover"       // "Turn" / "换手"
"backtest.runs.colAnnRet"         // "AnnRet" / "年化"
"backtest.runs.colParams"         // "params" / "参数"
"backtest.runs.colActions"        // "actions" / "操作"
"backtest.runs.baselineMark"      // tooltip: "current baseline" / "当前参照"
"backtest.runs.refill"            // aria-label: "Refill form from this run" / "用此运行回填表单"
"backtest.runs.pin"               // aria-label: "Pin as baseline" / "钉为参照"
"backtest.runs.zoo"               // aria-label: "Save to Zoo" / "保存到 Zoo"
```

Reuse existing keys where they fit; add new keys only for new wording. Add identical structure to both zh and en blocks.

- [ ] **Step 3: tsc clean**

`cd frontend && npx tsc --noEmit` → no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/i18n.ts
git commit -m "feat(backtest): i18n keys for redesigned page (verdict/runs/groups/actions)"
```

---

### Task 3: BacktestFormSticky

**Files:**
- Create: `frontend/src/components/backtest/BacktestFormSticky.tsx`

Sticky-top form. Expression textarea + 3 visible params + Advanced 6-field collapsible + RUN button.

- [ ] **Step 1: Read precedent**

```bash
sed -n '160,240p' "frontend/src/app/(dashboard)/backtest/page.tsx"   # current form region
cat frontend/src/components/alpha/HypothesisInputCard.tsx | head -50  # style precedent
```

- [ ] **Step 2: Implement**

A `"use client"` component. Props: full session state (params, setParams, isRunning, runOnce). Layout:
- `position: sticky top-0 z-30` container; backdrop-blur or solid bg-tm-bg-2.
- Row 1: full-width expression textarea (1 row collapsed, grow to 3-4 rows on focus).
- Row 2 (visible): direction select + topPct number + universe select + [+] Advanced toggle + RUN button (right end).
- Row 2.5 (when Advanced open): bot_pct + lookback + benchmark + neutralize toggle + cost_bps + mode select. Below row 2.
- All labels route through `t(locale, "backtest.action.*")` etc.
- `RUN BACKTEST` button = `bg-tm-accent text-tm-bg`, disabled when `params.expression.trim().length === 0 || isRunning`.

The Universe list = ["CSI300", "CSI500", "SP500", "custom"] per /alpha T2 discovery. Confirm by grep.

- [ ] **Step 3: tsc + lint clean**

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/backtest/BacktestFormSticky.tsx
git commit -m "feat(backtest): BacktestFormSticky with 4 visible + Advanced 6-field collapsible"
```

---

### Task 4: BacktestVerdictBar

**Files:**
- Create: `frontend/src/components/backtest/BacktestVerdictBar.tsx`

5-metric bar with delta arrows + traffic-light + 2 actions.

- [ ] **Step 1: Read precedent** (alpha's VerdictBar.tsx + the just-finished useBacktestSession's `deltas` shape).

- [ ] **Step 2: Implement**

Props: runState, currentRun (Run | null), deltas (5 MetricDelta | null), thresholds, baselineRunId, onSaveToZoo, onTogglePin.

States to render:
- `runState.kind === "idle"` → muted "Run a backtest to see results."
- `running` → spinner + ETA text.
- `error` → red bar with message + Re-run.
- `ok` AND recentRuns.length <= 1 → 5 metrics + marks, no delta arrows.
- `ok` AND recentRuns.length >= 2 → 5 metrics + marks + delta arrows. Each arrow:
  - `↑` green if betterThanBaseline + arrow=up; `↑` red if !better + arrow=up (e.g. turnover went up = bad)
  - Same convention for `↓` and `→`.
  - Arrow color drives from `betterThanBaseline` flag; arrow direction drives from `arrow` field. (The arrow's UP/DOWN semantic is decoupled from "good/bad" semantic.)
- Two action buttons: `[SAVE TO ZOO]` always when currentRun exists; `[PIN AS BASELINE]` toggles. When `baselineRunId === currentRun.id`, button reads `[UNPIN]`.

Threshold marks (✓ / ⚠ / ✗): same logic as /alpha but extended to 5 metrics per spec §8.2.

- [ ] **Step 3: tsc + lint clean**

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/backtest/BacktestVerdictBar.tsx
git commit -m "feat(backtest): VerdictBar with 5-metric delta arrows + SAVE + PIN"
```

---

### Task 5: BacktestEvidenceGrid + 3 evidence panes

**Files:**
- Create: `frontend/src/components/backtest/BacktestEvidenceGrid.tsx`
- Create: `frontend/src/components/backtest/EquityCurvePane.tsx`
- Create: `frontend/src/components/backtest/DrawdownPane.tsx`
- Create: `frontend/src/components/backtest/WalkforwardPane.tsx`

Each pane reuses existing chart code from `(dashboard)/backtest/page.tsx`. The wrappers add 4 render branches (waiting / loading / ok / error) + skeleton.

- [ ] **Step 1: Read existing chart code**

```bash
grep -nE "AreaChart|LineChart|BarChart|<Equity|Drawdown|WalkForward|recharts" "frontend/src/app/(dashboard)/backtest/page.tsx" | head -10
```

Identify the line ranges where each chart's render JSX lives. Note the data shape it reads from `FactorBacktestResponse`.

- [ ] **Step 2: Implement each pane (mirror /alpha's pane pattern)**

Each pane has 4 states: waiting (skeleton), loading (skeleton with extra animation), ok (real chart), error (message + Retry).

The EquityCurvePane reads `raw.equity_curve` (verify field path); DrawdownPane reads `raw.drawdown_series`; WalkforwardPane reads `raw.walkforward_folds` or whatever fold-IC field the response carries. Adapt to real names.

- [ ] **Step 3: Implement BacktestEvidenceGrid**

A grid container: `grid grid-cols-1 gap-3 lg:grid-cols-3`. Renders the 3 panes side-by-side on wide screens, stacked on narrow.

- [ ] **Step 4: tsc + lint clean**

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/backtest/BacktestEvidenceGrid.tsx frontend/src/components/backtest/EquityCurvePane.tsx frontend/src/components/backtest/DrawdownPane.tsx frontend/src/components/backtest/WalkforwardPane.tsx
git commit -m "feat(backtest): EvidenceGrid + Equity/Drawdown/Walkforward panes"
```

---

### Task 6: BacktestAnalyticsGroups + 4 group accordions + 9 sub-pane wrappers

**Files:**
- Create: `frontend/src/components/backtest/BacktestAnalyticsGroups.tsx`
- Create: 9 sub-pane wrapper files (or co-locate inside the groups file if smaller)

This is the largest content task. Each sub-pane is a THIN ADAPTER over the existing pane content from current `page.tsx`. Do NOT rewrite chart logic; just wrap.

- [ ] **Step 1: Map existing panes to new groups**

Per spec §7 component tree:
- RISK group: RiskAttributionPane + WorstDrawdownsPane + WinLossDistributionPane (current page lines ~325, ~525, ~645)
- REGIME group: TrainTestSplitPane + RegimeBreakdownPane (current page lines ~383, ~1103)
- HOLDINGS group: PortfolioTodayPane + PositionContributionPane (current page lines ~738, ~1017)
- OPERATIONS group: TurnoverProfilePane + DailyBreakdownPane (current page lines ~890, ~1286)

For each, identify the data fields consumed from `FactorBacktestResponse` and the render JSX.

- [ ] **Step 2: Implement GroupAccordion component**

A reusable accordion: open/closed state via useState. Header shows title + `(N panes)` + optional `⚠` badge with reason tooltip. Click toggles. Closed = compact 1-line; open = stacked children.

Badge logic (per spec §8.4):
- RISK badge ⚠ when `metrics.maxDD < -0.25` OR `raw.test_metrics.hit_rate < 0.4`
- OPERATIONS badge ⚠ when `metrics.turnover > 0.6`
- REGIME, HOLDINGS no badge in v1.

- [ ] **Step 3: Implement 9 sub-pane wrappers**

Each wrapper is ~30-80 lines. The render logic is copy-paste from current page.tsx with minor adaptations:
- Replace inline state with prop-receive.
- Strip the outer `<TmPane>` (the new GroupAccordion provides the chrome).
- Route every visible string through `t(locale, "backtest.*")`.

- [ ] **Step 4: Implement BacktestAnalyticsGroups**

Wraps the 4 GroupAccordion instances with proper data props.

- [ ] **Step 5: tsc + lint clean**

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/backtest/BacktestAnalyticsGroups.tsx frontend/src/components/backtest/*Pane.tsx frontend/src/components/backtest/GroupAccordion.tsx
git commit -m "feat(backtest): AnalyticsGroups with 4 grouped accordions and 9 sub-pane wrappers"
```

---

### Task 7: RecentRunsTable

**Files:**
- Create: `frontend/src/components/backtest/RecentRunsTable.tsx`

Session-only history table; per-row refill/pin/zoo actions.

- [ ] **Step 1: Implement**

A `"use client"` component. Props: recentRuns (Run[]), baselineRunId, onRefill, onTogglePin, onSaveToZoo.

Table structure per spec §8.5:
- 10 rows max; empty state when empty.
- Columns: Run # / ★ marker / Sharpe / maxDD / IC / Turnover / AnnRet / params summary / actions.
- ★ shown if `run.id === baselineRunId`.
- Per-row actions = 3 lucide icon buttons: `RotateCcw` (refill) / `Star` (pin/unpin toggle, filled when active) / `Bookmark` (save to zoo).
- Each action triggers via prop callback + fires a `toast.success` with appropriate copy and Undo where applicable.

`params summary` column: condensed string like `"top=30% dir=LS univ=SP500"`. Derive from `run.params`.

- [ ] **Step 2: tsc + lint clean**

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/backtest/RecentRunsTable.tsx
git commit -m "feat(backtest): RecentRunsTable session-only with refill/pin/zoo actions"
```

---

### Task 8: page.tsx rewrite

**Files:**
- Rewrite: `frontend/src/app/(dashboard)/backtest/page.tsx`

The new page is a thin orchestrator wiring useBacktestSession + 5 components. Estimated ~150 lines (down from 1368).

- [ ] **Step 1: Read existing PrefillPayload + Zoo integration**

```bash
grep -nE "prefill|PrefillPayload|addToZoo|saveZoo|removeFromZoo" "frontend/src/app/(dashboard)/backtest/page.tsx" frontend/src/lib/factor-zoo.ts | head -20
```

Identify:
- How PrefillPayload arrives (URL param? sessionStorage? React state from /alpha "Run Backtest" link).
- The exact addToZoo signature for backtest results.
- removeFromZoo for Undo support.

- [ ] **Step 2: Write the new page**

```tsx
"use client";

import { useCallback, useEffect } from "react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { useToast } from "@/components/ui/toast";
import { useBacktestSession } from "@/components/backtest/useBacktestSession";
import { BacktestFormSticky } from "@/components/backtest/BacktestFormSticky";
import { BacktestVerdictBar } from "@/components/backtest/BacktestVerdictBar";
import { BacktestEvidenceGrid } from "@/components/backtest/BacktestEvidenceGrid";
import { BacktestAnalyticsGroups } from "@/components/backtest/BacktestAnalyticsGroups";
import { RecentRunsTable } from "@/components/backtest/RecentRunsTable";
import { addToZoo, removeFromZoo } from "@/lib/factor-zoo";

export default function BacktestPage() {
  const { locale } = useLocale();
  const { toast } = useToast();
  const session = useBacktestSession();

  // PrefillPayload handling: paste from existing page.tsx ~line 96-108
  // (read during Step 1 above).
  useEffect(() => {
    // ... real prefill consumption ...
  }, []);

  const handleSaveToZoo = useCallback((runId?: string) => {
    const run = runId
      ? session.recentRuns.find(r => r.id === runId)
      : session.currentRun;
    if (!run) return;
    const saved = addToZoo({
      // real shape from factor-zoo.ts addToZoo signature
      name: run.params.expression.slice(0, 60),
      expression: run.params.expression,
      hypothesis: "",
      intuition: "",
      headlineMetrics: {
        testSharpe: run.metrics.sharpe ?? 0,
        totalReturn: run.raw.test_metrics?.total_return ?? 0,
        testIc: run.metrics.ic ?? 0,
      },
    });
    toast.success(t(locale, "backtest.runs.savedToast" as Parameters<typeof t>[1]), {
      action: {
        label: t(locale, "backtest.runs.undo" as Parameters<typeof t>[1]),
        onClick: () => removeFromZoo(saved.id),
      },
    });
  }, [session, toast, locale]);

  return (
    <main className="flex flex-col">
      <BacktestFormSticky
        params={session.params}
        setParams={session.setParams}
        isRunning={session.isRunning}
        onRun={session.runOnce}
      />
      <div className="flex flex-col gap-4 p-4">
        <BacktestVerdictBar
          runState={session.runState}
          currentRun={session.currentRun}
          deltas={session.deltas}
          thresholds={session.thresholds}
          baselineRunId={session.baselineRunId}
          onSaveToZoo={() => handleSaveToZoo()}
          onTogglePin={() => session.currentRun && session.togglePin(session.currentRun.id)}
        />
        <BacktestEvidenceGrid
          runState={session.runState}
          currentRun={session.currentRun}
        />
        <BacktestAnalyticsGroups
          currentRun={session.currentRun}
        />
        <RecentRunsTable
          runs={session.recentRuns}
          baselineRunId={session.baselineRunId}
          onRefill={session.refillFromRun}
          onTogglePin={session.togglePin}
          onSaveToZoo={handleSaveToZoo}
        />
      </div>
    </main>
  );
}
```

- [ ] **Step 3: Fill the 3 critical placeholders**

Same caveat as /alpha T6: do NOT ship placeholders. Before commit:
1. PrefillPayload consumption code (transplant from old page.tsx).
2. addToZoo signature + payload (verify in factor-zoo.ts).
3. removeFromZoo behavior (confirm available for Undo).

- [ ] **Step 4: tsc + lint + build clean**

```bash
cd frontend && npx tsc --noEmit && npx next lint && npm run build 2>&1 | tail -15
```
Pre-existing `/picks` ECONNREFUSED is acceptable; any new error on `/backtest` is not.

- [ ] **Step 5: Visual sanity (manual dev server)**

`npm run dev` then open `/backtest`. Verify:
- Sticky form holds position on scroll.
- Empty state shows "Run a backtest to see results."
- Triggering a run (with a valid expression typed in) populates verdict bar + 3 evidence panes + adds row to RECENT RUNS.
- Triggering a second run shows delta arrows on verdict bar.
- Clicking PIN AS BASELINE on the 2nd run swaps the baseline (★ mark moves).
- All visible strings change when locale toggles.

- [ ] **Step 6: Commit**

```bash
git add "frontend/src/app/(dashboard)/backtest/page.tsx"
git commit -m "feat(backtest): page.tsx rewritten as thin orchestrator (1368 -> ~150 lines)"
```

---

### Task 9: deploy + smoke + visual verification

- [ ] **Step 1: push**

```bash
git push
```

- [ ] **Step 2: Visual smoke against deployed frontend**

Open `/backtest` in production. Verify the same 5 checks from Task 8 Step 5 against the prod backend. Specifically:
- Sticky form stays sticky.
- Run a real backtest with a valid expression; results populate progressively.
- Toggle locale; every visible string changes.
- Click SAVE TO ZOO; toast appears bottom-right with Undo action.
- Click PIN AS BASELINE on the 2nd run; delta arrows recompute on the 3rd.
- Open RISK DETAIL accordion; sub-panes render existing chart logic.

- [ ] **Step 3: Report any cross-cutting regression**

If any pane content differs from the pre-redesign behavior (e.g. a chart silently dropped a field, a number formatter changed), file a fix commit referencing the affected sub-pane.

---

## Self-Review

**Spec coverage (all 8 brainstorm decisions):**
- 1 (mode tuning) + 2 (sticky form): T3 + T8 (sticky form layout + RECENT RUNS at bottom).
- 3 (5 metrics + delta + pin): T1 `deltas` derivation + T4 VerdictBar with `↑/↓/→` + togglePin.
- 4 (EQUITY + DRAWDOWN + WALKFORWARD evidence): T5 grid + 3 panes.
- 5 (session-only N=10 + Zoo/baseline independent): T1 hook state + T7 RecentRunsTable + T8 onSaveToZoo.
- 6 (4 grouped accordions, 9 sub-panes): T6.
- 7 (badge-not-auto-expand): T6 GroupAccordion badge logic.
- 8 (4 visible + Advanced 6 form): T3.

**Cross-cutting conventions audit (per `feedback_cross_cutting_conventions_audit`):**
- i18n: T2 adds new keys; every component task reuses existing keys.
- Font: `font-tm-mono` applied in every component task (T3-T7).
- Layout wrappers: `<TmPane>` reused for evidence panes + RecentRunsTable.
- Locale-aware data: form labels + button labels + pane titles route through `t(locale, ...)`.
- Sidebar nav: unchanged.

**10 UI/UX principles re-check (per `feedback_ui_ux_first_principles`):**
- Intent alignment: T3 sticky form + T8 verdict bar adjacency.
- Cognitive load: T6 grouped accordions hide 9 panes.
- Visibility: T4 spinner + delta arrows; T7 toast on every action.
- Forgiveness: T4 pin is toggle; T7 actions reversible; toast Undo on save.
- Affordance: T4 single accent button (RUN); T7 tertiary icon buttons.
- Design disappears: T8 thin page.tsx; T6 sub-panes look uniform via GroupAccordion wrapper.
- No manual needed: T3 4 visible fields are tuning's recurring params.
- Respects user time: T4 inline spinner + ETA copy; T7 in-pane actions.
- No dark patterns: T4 thresholds visible on hover.
- One Primary Action: T3 RUN BACKTEST is the only accent button.

**Anti-pattern guardrails:**
- Silent exception: T1 runOnce catches into error state; T4 surfaces via verdict bar + T7 toast.
- Token correctness: all tasks specify verified `tm-*` tokens.
- Grep call chain: T1 + T5 explicitly say "read real field path before writing" (matches /alpha T1 lesson).
- Cross-cutting conventions: T2 dedicated i18n task; every component task mentions `useLocale` wiring.

**Out of scope:**
- Parameter-sweep automation (spec §12).
- Diff view between two pinned runs.
- Backend persistence of RECENT RUNS.

---

## Execution Handoff

Plan complete. Two execution options:

**1. Subagent-Driven (recommended)** — fresh subagent per task with two-stage review, consistent with /alpha redesign.

**2. Inline Execution** — same-session batched execution.

Pick approach to proceed.
