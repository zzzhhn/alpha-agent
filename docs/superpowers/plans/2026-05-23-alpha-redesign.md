# /alpha Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `/alpha/page.tsx` (1632 lines, 11 panes, 12 state flags) with a focused decision-session page driven by a 2-call sequential chain (`/alpha/translate` returns spec + smoke together, then `/alpha/backtest`). Top-level layout = single Primary Action button + verdict bar + 3 evidence panes + collapsed analytics. Built bottom-up: state hook -> 4 leaf components -> page orchestrator -> deploy.

**Architecture:** A `useAlphaChain` hook owns the sequential 2-call orchestration + ChainState + PaneState. Each evidence pane (SpecPane, SmokePane, BacktestPane) is independently rendered from chain state. The VerdictBar derives from chain state + the smoke/backtest metrics. The AnalyticsAccordion auto-expands specific panes when smoke / provenance warning flags fire. The page.tsx shrinks from a stateful monolith into a thin composition layer.

**Tech Stack:** Next.js 14 App Router, TypeScript, Tailwind (`tm-*` tokens), lucide-react, the Phase UX-0 `useToast` for Save feedback. No new deps. Reuses existing `translateHypothesis` + `runFactorBacktest` API clients.

**API shape verified (pre-flight grep):** `HypothesisTranslateResponse` already contains `smoke: SmokeReport`. SPEC + SMOKE fill from one API call; BACKTEST is the second. State machine: `idle -> translating -> backtesting -> done` (or `error` per stage).

---

## Dependencies + grounding (read first during Task 1)

- Current `/alpha/page.tsx` (1632 lines) — read in chunks to learn: the textarea state shape, how `translateHypothesis` is called (line ~135), what fields `HypothesisTranslateResponse` carries (`spec`, `smoke`, `provenance`, others), the history/favorites loading pattern (~line 105-110), example chips data source (`FACTOR_EXAMPLES` constant).
- `frontend/src/lib/types.ts:276` defines `HypothesisTranslateResponse`; line 278 confirms `smoke: SmokeReport` is in the same response.
- `frontend/src/lib/api.ts:263` defines `translateHypothesis`; the backtest helper is `runFactorBacktest`. Both already auth-injected by middleware.
- Phase UX-0 Toast: `frontend/src/components/ui/toast/` exports `useToast`. The `useToast` hook returns `{ toast: { success, error, info, dismiss } }`. Error toasts are sticky by default; success/info auto-dismiss.
- Token reality (from Phase UX-0): use `tm-bg-2` (card bg), `tm-rule` (borders), `tm-fg` (primary text), `tm-fg-2` (secondary), `tm-muted`, `tm-accent`, `tm-pos`, `tm-neg`, `tm-warn`, `tm-info`. Do NOT use `tm-card`, `tm-line`, `tm-fg-1`.
- Brainstorm decisions: see `docs/superpowers/specs/2026-05-23-alpha-redesign-design.md` for the 9 locked decisions + threshold table.
- Anti-pattern guardrails: grep call-chain before assuming a token / hook / component lives where you think it does (3c lesson). No `bg-tm-card` (Tailwind silently drops unknown classes). No `console.error`-only error handlers; surface via toast or pane state.

---

## File Structure

- `frontend/src/components/alpha/useAlphaChain.ts` (new): state hook orchestrating translate + backtest.
- `frontend/src/components/alpha/types.ts` (new): ChainState, PaneState, derived types.
- `frontend/src/components/alpha/HypothesisInputCard.tsx` (new).
- `frontend/src/components/alpha/VerdictBar.tsx` (new).
- `frontend/src/components/alpha/EvidencePaneGrid.tsx` (new) + sub-files `SpecPane.tsx` / `SmokePane.tsx` / `BacktestPane.tsx`.
- `frontend/src/components/alpha/AnalyticsAccordion.tsx` (new).
- `frontend/src/app/(dashboard)/alpha/page.tsx` (rewrite from 1632 -> ~150 lines).

Existing files NOT touched: `frontend/src/lib/api.ts`, `frontend/src/lib/types.ts`, the `(dashboard)/alpha/loading.tsx` from Phase UX-0.

---

### Task 1: types + `useAlphaChain` state hook

**Files:**
- Create: `frontend/src/components/alpha/types.ts`
- Create: `frontend/src/components/alpha/useAlphaChain.ts`

This task ships PURE LOGIC: types + a hook that holds chain state, exposes `start(text, universe)` to kick off the 2-call sequence, and exposes the derived per-pane state + verdict-bar inputs. No JSX, no DOM. Visual verification is downstream.

- [ ] **Step 1: Define types** at `frontend/src/components/alpha/types.ts`:

```typescript
import type {
  FactorBacktestResponse,
  FactorUniverse,
  HypothesisTranslateResponse,
} from "@/lib/types";

export type ChainState =
  | { kind: "idle" }
  | { kind: "translating" }
  | { kind: "backtesting"; translate: HypothesisTranslateResponse }
  | { kind: "done"; translate: HypothesisTranslateResponse; backtest: FactorBacktestResponse }
  | { kind: "translate_error"; message: string }
  | { kind: "backtest_error"; translate: HypothesisTranslateResponse; message: string };

export type PaneState = "waiting" | "loading" | "ok" | "error";

export interface ChainPaneStates {
  spec: PaneState;
  smoke: PaneState;
  backtest: PaneState;
}

export interface VerdictMetrics {
  ic: number | null;
  sharpe: number | null;
  maxDrawdown: number | null;
}

export interface ThresholdMark {
  status: "ok" | "warn" | "bad";
  threshold: string;
}

export interface ThresholdEval {
  ic: ThresholdMark | null;
  sharpe: ThresholdMark | null;
  maxDrawdown: ThresholdMark | null;
}
```

- [ ] **Step 2: Implement `useAlphaChain`** at `frontend/src/components/alpha/useAlphaChain.ts`:

```typescript
"use client";

import { useCallback, useMemo, useState } from "react";
import { runFactorBacktest, translateHypothesis } from "@/lib/api";
import type { FactorUniverse } from "@/lib/types";
import type {
  ChainPaneStates,
  ChainState,
  ThresholdEval,
  VerdictMetrics,
} from "./types";

const IC_OK = 0.02;
const SHARPE_OK = 1.0;
const SHARPE_WARN = 0.5;
const MAXDD_OK = -0.15;
const MAXDD_BAD = -0.25;

function evalThresholds(m: VerdictMetrics): ThresholdEval {
  return {
    ic: m.ic === null ? null : {
      status: m.ic >= IC_OK ? "ok" : m.ic > 0 ? "warn" : "bad",
      threshold: "threshold >=0.02 considered useful",
    },
    sharpe: m.sharpe === null ? null : {
      status: m.sharpe >= SHARPE_OK ? "ok" : m.sharpe >= SHARPE_WARN ? "warn" : "bad",
      threshold: "threshold >=1.0 considered viable",
    },
    maxDrawdown: m.maxDrawdown === null ? null : {
      status: m.maxDrawdown >= MAXDD_OK ? "ok" : m.maxDrawdown >= MAXDD_BAD ? "warn" : "bad",
      threshold: "threshold >=-15% considered acceptable",
    },
  };
}

function paneStates(s: ChainState): ChainPaneStates {
  switch (s.kind) {
    case "idle": return { spec: "waiting", smoke: "waiting", backtest: "waiting" };
    case "translating": return { spec: "loading", smoke: "loading", backtest: "waiting" };
    case "backtesting": return { spec: "ok", smoke: "ok", backtest: "loading" };
    case "done": return { spec: "ok", smoke: "ok", backtest: "ok" };
    case "translate_error": return { spec: "error", smoke: "waiting", backtest: "waiting" };
    case "backtest_error": return { spec: "ok", smoke: "ok", backtest: "error" };
  }
}

function metrics(s: ChainState): VerdictMetrics {
  const ic = s.kind === "backtesting" || s.kind === "done" || s.kind === "backtest_error"
    ? s.translate.smoke?.ic_mean ?? null : null;
  const bt = s.kind === "done" ? s.backtest : null;
  return {
    ic,
    sharpe: bt?.metrics?.sharpe ?? null,
    maxDrawdown: bt?.metrics?.max_drawdown ?? null,
  };
}

export function useAlphaChain() {
  const [state, setState] = useState<ChainState>({ kind: "idle" });

  const start = useCallback(async (text: string, universe: FactorUniverse) => {
    setState({ kind: "translating" });
    let translate: Awaited<ReturnType<typeof translateHypothesis>>;
    try {
      translate = await translateHypothesis({ text, universe });
    } catch (e) {
      setState({ kind: "translate_error", message: e instanceof Error ? e.message : String(e) });
      return;
    }
    setState({ kind: "backtesting", translate });
    try {
      const backtest = await runFactorBacktest({
        expression: translate.spec.expression,
        universe,
        direction: "long_short",
      });
      setState({ kind: "done", translate, backtest });
    } catch (e) {
      setState({
        kind: "backtest_error",
        translate,
        message: e instanceof Error ? e.message : String(e),
      });
    }
  }, []);

  const retryBacktest = useCallback(async () => {
    if (state.kind !== "backtest_error" && state.kind !== "done") return;
    const translate = state.translate;
    setState({ kind: "backtesting", translate });
    try {
      const backtest = await runFactorBacktest({
        expression: translate.spec.expression,
        universe: translate.spec.universe as FactorUniverse,
        direction: "long_short",
      });
      setState({ kind: "done", translate, backtest });
    } catch (e) {
      setState({
        kind: "backtest_error",
        translate,
        message: e instanceof Error ? e.message : String(e),
      });
    }
  }, [state]);

  const reset = useCallback(() => setState({ kind: "idle" }), []);

  return useMemo(() => ({
    state,
    panes: paneStates(state),
    metrics: metrics(state),
    thresholds: evalThresholds(metrics(state)),
    start,
    retryBacktest,
    reset,
    isLoading: state.kind === "translating" || state.kind === "backtesting",
  }), [state, start, retryBacktest, reset]);
}
```

NOTE: the real shape of `translate.spec.universe`, `translate.spec.expression`, `backtest.metrics` must be confirmed by reading `frontend/src/lib/types.ts`. The structure above is the expected layout per the spec; ADAPT if the real types differ (e.g., `metrics.sharpe` vs `metrics.sharpe_ratio`).

- [ ] **Step 3: tsc clean**

```bash
cd frontend && npx tsc --noEmit
```
Expected: zero new errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/alpha/types.ts frontend/src/components/alpha/useAlphaChain.ts
git commit -m "feat(alpha): ChainState + useAlphaChain hook for redesigned alpha page"
```

---

### Task 2: HypothesisInputCard

**Files:**
- Create: `frontend/src/components/alpha/HypothesisInputCard.tsx`

A `"use client"` component containing: textarea, character count badge, History dropdown (popover), Examples chip row (visible only in empty state), Universe selector, and the Primary Action button "TRANSLATE & BACKTEST".

- [ ] **Step 1: Read precedents**

```bash
sed -n '400,470p' "frontend/src/app/(dashboard)/alpha/page.tsx"
grep -nE "FACTOR_EXAMPLES|favorites|recent|HypothesisHistoryEntry" frontend/src/lib/*.ts "frontend/src/app/(dashboard)/alpha/page.tsx" | head -20
```
Identify how the current page populates Examples (constant) + History (API or localStorage), so the new component can reuse the same data plumbing.

- [ ] **Step 2: Implement**

```tsx
"use client";

import { ChevronDown, History, Sparkles } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { FactorUniverse } from "@/lib/types";

interface Props {
  text: string;
  onTextChange: (s: string) => void;
  universe: FactorUniverse;
  onUniverseChange: (u: FactorUniverse) => void;
  onSubmit: () => void;
  disabled: boolean;
  examples: ReadonlyArray<{ label: string; text: string }>;
  history: ReadonlyArray<{ id: string; text: string; created_at: string }>;
  onHistorySelect: (entry: { text: string }) => void;
}

const UNIVERSES: FactorUniverse[] = ["SP500", "SP100"];

export function HypothesisInputCard(p: Props) {
  const [historyOpen, setHistoryOpen] = useState(false);
  const popoverRef = useRef<HTMLDivElement | null>(null);

  // Close history popover on outside click.
  useEffect(() => {
    if (!historyOpen) return;
    function handler(e: MouseEvent) {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        setHistoryOpen(false);
      }
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [historyOpen]);

  const empty = p.text.trim().length === 0;

  return (
    <section className="flex flex-col gap-3 rounded border border-tm-rule bg-tm-bg-2 p-4">
      <header className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-tm-fg">HYPOTHESIS INPUT</h2>
        <div className="relative" ref={popoverRef}>
          <button
            onClick={() => setHistoryOpen(o => !o)}
            className="inline-flex items-center gap-1 rounded border border-tm-rule px-2 py-1 text-xs text-tm-fg-2 hover:text-tm-fg"
          >
            <History className="h-3.5 w-3.5" strokeWidth={1.75} />
            <span>History</span>
            <ChevronDown className="h-3 w-3" strokeWidth={1.75} />
          </button>
          {historyOpen && (
            <div className="absolute right-0 top-full z-10 mt-1 w-[360px] max-h-[400px] overflow-y-auto rounded border border-tm-rule bg-tm-bg-2 shadow-lg">
              {p.history.length === 0 ? (
                <div className="px-3 py-4 text-xs text-tm-muted">No saved hypotheses yet.</div>
              ) : (
                p.history.map(h => (
                  <button
                    key={h.id}
                    onClick={() => { p.onHistorySelect(h); setHistoryOpen(false); }}
                    className="block w-full px-3 py-2 text-left text-xs text-tm-fg-2 hover:bg-tm-bg-3 hover:text-tm-fg"
                  >
                    <div className="line-clamp-2">{h.text}</div>
                    <div className="mt-1 text-[10px] text-tm-muted">{h.created_at}</div>
                  </button>
                ))
              )}
            </div>
          )}
        </div>
      </header>

      <textarea
        value={p.text}
        onChange={e => p.onTextChange(e.target.value)}
        placeholder="e.g. 12-month momentum minus 6-month volatility, neutralized by sector"
        className="min-h-[96px] resize-y rounded border border-tm-rule bg-tm-bg p-3 font-mono text-sm text-tm-fg placeholder:text-tm-muted focus:border-tm-accent focus:outline-none"
      />

      {empty && (
        <div className="flex flex-wrap gap-2">
          <span className="text-xs text-tm-muted">Examples:</span>
          {p.examples.map(ex => (
            <button
              key={ex.label}
              onClick={() => p.onTextChange(ex.text)}
              className="inline-flex items-center gap-1 rounded-full border border-tm-rule px-2.5 py-0.5 text-xs text-tm-fg-2 hover:border-tm-accent hover:text-tm-accent"
            >
              <Sparkles className="h-3 w-3" strokeWidth={1.75} />
              {ex.label}
            </button>
          ))}
        </div>
      )}

      <div className="flex items-center justify-between gap-3">
        <div className="text-xs text-tm-muted">{p.text.length} chars</div>
        <div className="flex items-center gap-2">
          <select
            value={p.universe}
            onChange={e => p.onUniverseChange(e.target.value as FactorUniverse)}
            className="rounded border border-tm-rule bg-tm-bg px-2 py-1 text-xs text-tm-fg"
          >
            {UNIVERSES.map(u => <option key={u} value={u}>{u}</option>)}
          </select>
          <button
            onClick={p.onSubmit}
            disabled={p.disabled || empty}
            className="rounded bg-tm-accent px-4 py-2 text-sm font-semibold text-tm-bg disabled:opacity-50"
          >
            TRANSLATE & BACKTEST
          </button>
        </div>
      </div>
    </section>
  );
}
```

If the project does NOT have a `bg-tm-bg` token, fall back to `bg-tm-bg-3` (verified in the Phase UX-0 grep). If `text-tm-bg` (for button text against accent bg) is wrong, use whatever accent-on-foreground token the existing Button.tsx uses.

- [ ] **Step 3: tsc + lint clean**

```bash
cd frontend && npx tsc --noEmit && npx next lint
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/alpha/HypothesisInputCard.tsx
git commit -m "feat(alpha): HypothesisInputCard (textarea + history dropdown + examples + primary button)"
```

---

### Task 3: VerdictBar

**Files:**
- Create: `frontend/src/components/alpha/VerdictBar.tsx`

Renders a single horizontal bar derived from `useAlphaChain` output. 6 visual variants per the spec.

- [ ] **Step 1: Implement**

```tsx
"use client";

import { AlertCircle, Check, Loader2 } from "lucide-react";
import type { ChainState, ThresholdEval, VerdictMetrics } from "./types";

interface Props {
  state: ChainState;
  metrics: VerdictMetrics;
  thresholds: ThresholdEval;
  canSave: boolean;
  onSave: () => void;
  onReTranslate: () => void;
}

const MARK = {
  ok: <span className="ml-1 text-tm-pos">✓</span>,
  warn: <span className="ml-1 text-tm-warn">⚠</span>,
  bad: <span className="ml-1 text-tm-neg">✗</span>,
};

export function VerdictBar(p: Props) {
  const s = p.state;
  if (s.kind === "idle") {
    return (
      <section className="rounded border border-tm-rule bg-tm-bg-2 px-4 py-3 text-sm text-tm-muted">
        Submit a hypothesis above to start.
      </section>
    );
  }
  if (s.kind === "translate_error") {
    return (
      <section className="flex items-center justify-between rounded border border-tm-neg/40 bg-tm-neg/10 px-4 py-3">
        <div className="flex items-center gap-2 text-sm text-tm-neg">
          <AlertCircle className="h-4 w-4" strokeWidth={1.75} />
          <span>Translate failed: {s.message}</span>
        </div>
        <button
          onClick={p.onReTranslate}
          className="rounded border border-tm-neg/60 px-3 py-1 text-xs font-semibold text-tm-neg"
        >
          Re-translate
        </button>
      </section>
    );
  }
  const loading = s.kind === "translating" || s.kind === "backtesting";
  const stageText = s.kind === "translating"
    ? "Translating... (ETA ~10s)"
    : s.kind === "backtesting"
    ? "Backtesting..."
    : null;
  return (
    <section className="flex items-center justify-between rounded border border-tm-rule bg-tm-bg-2 px-4 py-3 text-sm">
      <div className="flex items-center gap-4">
        {loading && (
          <span className="flex items-center gap-1.5 text-tm-fg-2">
            <Loader2 className="h-3.5 w-3.5 animate-spin" strokeWidth={1.75} />
            {stageText}
          </span>
        )}
        {p.metrics.ic !== null && (
          <span title={p.thresholds.ic?.threshold ?? ""} className="cursor-help">
            IC={p.metrics.ic.toFixed(4)}
            {p.thresholds.ic && MARK[p.thresholds.ic.status]}
          </span>
        )}
        {p.metrics.sharpe !== null && (
          <span title={p.thresholds.sharpe?.threshold ?? ""} className="cursor-help">
            Sharpe={p.metrics.sharpe.toFixed(2)}
            {p.thresholds.sharpe && MARK[p.thresholds.sharpe.status]}
          </span>
        )}
        {p.metrics.maxDrawdown !== null && (
          <span title={p.thresholds.maxDrawdown?.threshold ?? ""} className="cursor-help">
            maxDD={(p.metrics.maxDrawdown * 100).toFixed(0)}%
            {p.thresholds.maxDrawdown && MARK[p.thresholds.maxDrawdown.status]}
          </span>
        )}
        {s.kind === "backtest_error" && (
          <span className="text-tm-warn">Backtest failed: {s.message.slice(0, 80)}</span>
        )}
      </div>
      {p.canSave && (
        <button
          onClick={p.onSave}
          className="inline-flex items-center gap-1 rounded bg-tm-accent px-3 py-1.5 text-sm font-semibold text-tm-bg"
        >
          <Check className="h-3.5 w-3.5" strokeWidth={1.75} />
          SAVE TO ZOO
        </button>
      )}
    </section>
  );
}
```

- [ ] **Step 2: tsc clean**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/alpha/VerdictBar.tsx
git commit -m "feat(alpha): VerdictBar with traffic-light thresholds + stage progress"
```

---

### Task 4: EvidencePaneGrid + 3 panes

**Files:**
- Create: `frontend/src/components/alpha/EvidencePaneGrid.tsx`
- Create: `frontend/src/components/alpha/SpecPane.tsx`
- Create: `frontend/src/components/alpha/SmokePane.tsx`
- Create: `frontend/src/components/alpha/BacktestPane.tsx`

Grid lays out the 3 panes (stacked on `sm`, 3-column on `lg`). Each pane has 4 render branches: waiting (skeleton), loading (skeleton), ok (content), error (error + Retry).

- [ ] **Step 1: Common pane skeleton helper**

Define a small inline helper inside each pane (no shared util needed):
```tsx
function Skeleton() {
  return (
    <div className="flex flex-col gap-2">
      <div className="h-3 w-3/4 animate-pulse rounded bg-tm-bg-3" />
      <div className="h-3 w-1/2 animate-pulse rounded bg-tm-bg-3" />
      <div className="h-16 w-full animate-pulse rounded bg-tm-bg-3" />
    </div>
  );
}
```

- [ ] **Step 2: SpecPane**

```tsx
"use client";
import type { HypothesisTranslateResponse } from "@/lib/types";
import type { PaneState } from "./types";

interface Props {
  state: PaneState;
  data: HypothesisTranslateResponse | null;
  errorMessage: string | null;
  onRetry?: () => void;
}

export function SpecPane({ state, data, errorMessage, onRetry }: Props) {
  return (
    <section className="flex flex-col gap-2 rounded border border-tm-rule bg-tm-bg-2 p-3">
      <h3 className="text-xs font-semibold uppercase text-tm-fg-2">SPEC</h3>
      {state === "waiting" || state === "loading" ? (
        <Skeleton />
      ) : state === "error" ? (
        <div className="text-xs text-tm-neg">
          <div>{errorMessage}</div>
          {onRetry && (
            <button onClick={onRetry} className="mt-2 rounded border border-tm-neg/40 px-2 py-0.5 text-tm-neg">
              Re-translate
            </button>
          )}
        </div>
      ) : data ? (
        <>
          <pre className="overflow-x-auto rounded bg-tm-bg-3 p-2 font-mono text-xs text-tm-fg">
            {data.spec.expression}
          </pre>
          <div className="text-[11px] text-tm-muted">
            operators: {data.spec.operators_used.join(", ")}
          </div>
        </>
      ) : null}
    </section>
  );
}

function Skeleton() { /* same as Step 1 */ }
```

- [ ] **Step 3: SmokePane**

```tsx
"use client";
import type { HypothesisTranslateResponse } from "@/lib/types";
import type { PaneState } from "./types";

interface Props {
  state: PaneState;
  data: HypothesisTranslateResponse["smoke"] | null;
  errorMessage: string | null;
  onRetry?: () => void;
}

export function SmokePane({ state, data, errorMessage, onRetry }: Props) {
  return (
    <section className="flex flex-col gap-2 rounded border border-tm-rule bg-tm-bg-2 p-3">
      <h3 className="text-xs font-semibold uppercase text-tm-fg-2">SMOKE PROBE</h3>
      {state === "waiting" || state === "loading" ? (
        <Skeleton />
      ) : state === "error" ? (
        <div className="text-xs text-tm-neg">
          <div>{errorMessage}</div>
          {onRetry && (
            <button onClick={onRetry} className="mt-2 rounded border border-tm-neg/40 px-2 py-0.5 text-tm-neg">
              Retry smoke
            </button>
          )}
        </div>
      ) : data ? (
        <>
          <div className="text-sm font-semibold text-tm-fg">
            IC = {data.ic_mean?.toFixed(4) ?? "n/a"}
          </div>
          {data.lookahead_leak && (
            <div className="rounded border border-tm-warn/40 bg-tm-warn/10 px-2 py-1 text-[11px] text-tm-warn">
              Lookahead leak suspected. See LOOKAHEAD.GUARD below.
            </div>
          )}
          <div className="text-[11px] text-tm-muted">
            ic_std={data.ic_std?.toFixed(4) ?? "n/a"} • n={data.n_observations ?? "n/a"}
          </div>
        </>
      ) : null}
    </section>
  );
}

function Skeleton() { /* same */ }
```

- [ ] **Step 4: BacktestPane**

```tsx
"use client";
import type { FactorBacktestResponse } from "@/lib/types";
import type { PaneState } from "./types";

interface Props {
  state: PaneState;
  data: FactorBacktestResponse | null;
  errorMessage: string | null;
  onRetry?: () => void;
}

export function BacktestPane({ state, data, errorMessage, onRetry }: Props) {
  return (
    <section className="flex flex-col gap-2 rounded border border-tm-rule bg-tm-bg-2 p-3">
      <h3 className="text-xs font-semibold uppercase text-tm-fg-2">BACKTEST</h3>
      {state === "waiting" || state === "loading" ? (
        <Skeleton />
      ) : state === "error" ? (
        <div className="text-xs text-tm-neg">
          <div>{errorMessage}</div>
          {onRetry && (
            <button onClick={onRetry} className="mt-2 rounded border border-tm-neg/40 px-2 py-0.5 text-tm-neg">
              Retry backtest
            </button>
          )}
        </div>
      ) : data ? (
        <>
          <div className="text-sm font-semibold text-tm-fg">
            Sharpe = {data.metrics.sharpe?.toFixed(2) ?? "n/a"}
          </div>
          <div className="text-[11px] text-tm-muted">
            maxDD = {data.metrics.max_drawdown !== undefined
              ? `${(data.metrics.max_drawdown * 100).toFixed(0)}%`
              : "n/a"}
            {" • "}
            ann ret = {data.metrics.annualized_return !== undefined
              ? `${(data.metrics.annualized_return * 100).toFixed(1)}%`
              : "n/a"}
          </div>
        </>
      ) : null}
    </section>
  );
}

function Skeleton() { /* same */ }
```

NOTE: `FactorBacktestResponse.metrics` field names must be confirmed from `frontend/src/lib/types.ts`. The names above (`sharpe`, `max_drawdown`, `annualized_return`) are the expected shape; ADAPT if different.

- [ ] **Step 5: EvidencePaneGrid**

```tsx
"use client";

import type { FactorBacktestResponse, HypothesisTranslateResponse } from "@/lib/types";
import { BacktestPane } from "./BacktestPane";
import { SmokePane } from "./SmokePane";
import { SpecPane } from "./SpecPane";
import type { ChainPaneStates, ChainState } from "./types";

interface Props {
  state: ChainState;
  panes: ChainPaneStates;
  onReTranslate: () => void;
  onRetryBacktest: () => void;
}

export function EvidencePaneGrid({ state, panes, onReTranslate, onRetryBacktest }: Props) {
  const translate: HypothesisTranslateResponse | null =
    "translate" in state ? state.translate :
    state.kind === "done" ? state.translate :
    null;
  const backtest: FactorBacktestResponse | null = state.kind === "done" ? state.backtest : null;
  const translateError = state.kind === "translate_error" ? state.message : null;
  const backtestError = state.kind === "backtest_error" ? state.message : null;

  return (
    <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
      <SpecPane state={panes.spec} data={translate} errorMessage={translateError} onRetry={onReTranslate} />
      <SmokePane state={panes.smoke} data={translate?.smoke ?? null} errorMessage={translateError} />
      <BacktestPane state={panes.backtest} data={backtest} errorMessage={backtestError} onRetry={onRetryBacktest} />
    </div>
  );
}
```

- [ ] **Step 6: tsc + lint clean**

```bash
cd frontend && npx tsc --noEmit && npx next lint
```

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/alpha/EvidencePaneGrid.tsx frontend/src/components/alpha/SpecPane.tsx frontend/src/components/alpha/SmokePane.tsx frontend/src/components/alpha/BacktestPane.tsx
git commit -m "feat(alpha): EvidencePaneGrid + Spec/Smoke/Backtest panes with skeleton/error states"
```

---

### Task 5: AnalyticsAccordion + 5 sub-panes

**Files:**
- Create: `frontend/src/components/alpha/AnalyticsAccordion.tsx`

5 sub-panes are rendered inside the accordion. Per the spec they are LookaheadGuard, ExpressionQuality, LlmProvenance, OperatorUsage, HistoryInsights. The accordion is collapsed by default; auto-expand fires on:
- `smoke.lookahead_leak === true` -> LookaheadGuard auto-expanded
- `smoke.expression_quality?.score < 0.6` -> ExpressionQuality auto-expanded
- `provenance.error !== null` -> LlmProvenance auto-expanded

Other panes only appear via the "Show all" toggle.

- [ ] **Step 1: Implement**

```tsx
"use client";

import { ChevronDown, ChevronRight } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { HypothesisTranslateResponse } from "@/lib/types";

interface Props {
  translate: HypothesisTranslateResponse | null;
}

function _hasLookaheadLeak(t: HypothesisTranslateResponse): boolean {
  return Boolean(t.smoke?.lookahead_leak);
}
function _hasQualityIssue(t: HypothesisTranslateResponse): boolean {
  const score = (t as any).quality?.score;
  return typeof score === "number" && score < 0.6;
}
function _hasProvenanceError(t: HypothesisTranslateResponse): boolean {
  return Boolean((t as any).provenance?.error);
}

export function AnalyticsAccordion({ translate }: Props) {
  const autoFlags = useMemo(() => {
    if (!translate) return { lookahead: false, quality: false, provenance: false };
    return {
      lookahead: _hasLookaheadLeak(translate),
      quality: _hasQualityIssue(translate),
      provenance: _hasProvenanceError(translate),
    };
  }, [translate]);

  const autoExpandedCount = (autoFlags.lookahead ? 1 : 0) + (autoFlags.quality ? 1 : 0) + (autoFlags.provenance ? 1 : 0);
  const [showAll, setShowAll] = useState(false);

  if (!translate) return null;

  return (
    <section className="flex flex-col gap-2">
      {autoFlags.lookahead && <LookaheadGuardPane translate={translate} />}
      {autoFlags.quality && <ExpressionQualityPane translate={translate} />}
      {autoFlags.provenance && <LlmProvenancePane translate={translate} />}
      <button
        onClick={() => setShowAll(s => !s)}
        className="inline-flex w-fit items-center gap-1 text-xs text-tm-fg-2 hover:text-tm-fg"
      >
        {showAll ? <ChevronDown className="h-3 w-3" strokeWidth={1.75} /> : <ChevronRight className="h-3 w-3" strokeWidth={1.75} />}
        {autoExpandedCount > 0
          ? showAll
            ? `Hide additional analysis`
            : `Show ${5 - autoExpandedCount} more analysis panes`
          : showAll
          ? `Hide analysis (5 panes)`
          : `Show analysis (5 panes)`}
      </button>
      {showAll && (
        <div className="flex flex-col gap-2">
          {!autoFlags.lookahead && <LookaheadGuardPane translate={translate} />}
          {!autoFlags.quality && <ExpressionQualityPane translate={translate} />}
          {!autoFlags.provenance && <LlmProvenancePane translate={translate} />}
          <OperatorUsagePane translate={translate} />
          <HistoryInsightsPane translate={translate} />
        </div>
      )}
    </section>
  );
}

function LookaheadGuardPane({ translate }: { translate: HypothesisTranslateResponse }) {
  return (
    <div className="rounded border border-tm-warn/40 bg-tm-warn/10 p-3 text-xs text-tm-warn">
      <div className="font-semibold">LOOKAHEAD GUARD</div>
      {translate.smoke?.lookahead_leak ? (
        <div className="mt-1">Leak detected. The expression may reference future returns.</div>
      ) : (
        <div className="mt-1 text-tm-muted">No leak detected.</div>
      )}
    </div>
  );
}

function ExpressionQualityPane({ translate }: { translate: HypothesisTranslateResponse }) {
  const score = (translate as any).quality?.score;
  return (
    <div className="rounded border border-tm-rule bg-tm-bg-2 p-3 text-xs text-tm-fg-2">
      <div className="font-semibold uppercase">Expression Quality</div>
      <div className="mt-1">Score: {typeof score === "number" ? score.toFixed(2) : "n/a"}</div>
    </div>
  );
}

function LlmProvenancePane({ translate }: { translate: HypothesisTranslateResponse }) {
  const prov = (translate as any).provenance;
  return (
    <div className="rounded border border-tm-rule bg-tm-bg-2 p-3 text-xs text-tm-fg-2">
      <div className="font-semibold uppercase">LLM Provenance</div>
      <div className="mt-1">
        provider: {prov?.provider ?? "—"} • model: {prov?.model ?? "—"}
        {" • "}
        latency: {prov?.latency_ms ?? "—"} ms
      </div>
      {prov?.error && <div className="mt-1 text-tm-neg">Error: {prov.error}</div>}
    </div>
  );
}

function OperatorUsagePane({ translate }: { translate: HypothesisTranslateResponse }) {
  return (
    <div className="rounded border border-tm-rule bg-tm-bg-2 p-3 text-xs text-tm-fg-2">
      <div className="font-semibold uppercase">Operator Usage</div>
      <div className="mt-1">{translate.spec.operators_used.join(", ")}</div>
    </div>
  );
}

function HistoryInsightsPane({ translate }: { translate: HypothesisTranslateResponse }) {
  const hi = (translate as any).history_insights;
  return (
    <div className="rounded border border-tm-rule bg-tm-bg-2 p-3 text-xs text-tm-fg-2">
      <div className="font-semibold uppercase">History Insights</div>
      <div className="mt-1">{hi ? JSON.stringify(hi) : "n/a"}</div>
    </div>
  );
}
```

The sub-panes use `(translate as any).provenance` / `.quality` / `.history_insights` only because we have NOT verified the exact shape from `types.ts`. During implementation: read `types.ts` to learn the real fields and remove the `any` casts. If a field doesn't exist on `HypothesisTranslateResponse`, drop that sub-pane or replace with a placeholder.

- [ ] **Step 2: tsc clean**

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/alpha/AnalyticsAccordion.tsx
git commit -m "feat(alpha): AnalyticsAccordion with smart auto-expand on warning flags"
```

---

### Task 6: page.tsx orchestration rewrite

**Files:**
- Rewrite: `frontend/src/app/(dashboard)/alpha/page.tsx`

The new page is a thin client component that wires the hook to the components. Estimated ~150 lines.

- [ ] **Step 1: Replace the entire file**

```tsx
"use client";

import { useCallback, useEffect, useState } from "react";
import { HypothesisInputCard } from "@/components/alpha/HypothesisInputCard";
import { VerdictBar } from "@/components/alpha/VerdictBar";
import { EvidencePaneGrid } from "@/components/alpha/EvidencePaneGrid";
import { AnalyticsAccordion } from "@/components/alpha/AnalyticsAccordion";
import { useAlphaChain } from "@/components/alpha/useAlphaChain";
import { useToast } from "@/components/ui/toast";
import type { FactorUniverse } from "@/lib/types";

// READ the current page.tsx (~line 100-130) to learn the actual
// FACTOR_EXAMPLES + history-loading mechanism, then reuse them verbatim
// here. Until verified, these are placeholders to satisfy the type system.
const FACTOR_EXAMPLES: ReadonlyArray<{ label: string; text: string }> = [
  { label: "momentum", text: "12-month momentum minus 6-month volatility, neutralized by sector" },
  { label: "reversal", text: "1-week reversal" },
  { label: "low-vol", text: "Negative 252-day realized volatility, equal-weighted" },
  { label: "value", text: "B/M ratio, sector-neutralized" },
  { label: "quality", text: "ROE minus net debt to equity" },
  { label: "size", text: "Inverse market cap, decile rank" },
];

export default function AlphaPage() {
  const [text, setText] = useState("");
  const [universe, setUniverse] = useState<FactorUniverse>("SP500");
  const [history, setHistory] = useState<ReadonlyArray<{ id: string; text: string; created_at: string }>>([]);
  const chain = useAlphaChain();
  const { toast } = useToast();

  // History load: reuse the existing endpoint. Read the current page.tsx
  // ~line 105-120 to learn the actual fetch path. Placeholder fetch below.
  useEffect(() => {
    // TODO during implementation: replace with the real history fetch.
    setHistory([]);
  }, []);

  const handleSubmit = useCallback(() => {
    if (text.trim().length === 0) return;
    chain.start(text, universe);
  }, [text, universe, chain]);

  const handleHistorySelect = useCallback((entry: { text: string }) => {
    setText(entry.text);
  }, []);

  const canSave =
    chain.state.kind === "done" ||
    chain.state.kind === "backtesting" ||
    chain.state.kind === "backtest_error";

  const handleSave = useCallback(async () => {
    if (!("translate" in chain.state) && chain.state.kind !== "done") return;
    const translate = chain.state.kind === "done" ? chain.state.translate :
                       "translate" in chain.state ? chain.state.translate : null;
    if (!translate) return;
    try {
      // TODO during implementation: call the real save-to-zoo endpoint.
      // const saved = await saveToZoo({ spec: translate.spec, ... });
      toast.success("Saved to Zoo", {
        action: { label: "Undo", onClick: () => {
          // TODO: deleteFromZoo(saved.id);
          toast.info("Save undone");
        }},
      });
    } catch (e) {
      toast.error(`Save failed: ${e instanceof Error ? e.message : String(e)}`);
    }
  }, [chain.state, toast]);

  const handleReTranslate = useCallback(() => {
    chain.reset();
    handleSubmit();
  }, [chain, handleSubmit]);

  const translate = "translate" in chain.state
    ? chain.state.translate
    : chain.state.kind === "done"
    ? chain.state.translate
    : null;

  return (
    <main className="flex flex-col gap-4 p-4">
      <HypothesisInputCard
        text={text}
        onTextChange={setText}
        universe={universe}
        onUniverseChange={setUniverse}
        onSubmit={handleSubmit}
        disabled={chain.isLoading}
        examples={FACTOR_EXAMPLES}
        history={history}
        onHistorySelect={handleHistorySelect}
      />
      <VerdictBar
        state={chain.state}
        metrics={chain.metrics}
        thresholds={chain.thresholds}
        canSave={canSave}
        onSave={handleSave}
        onReTranslate={handleReTranslate}
      />
      <EvidencePaneGrid
        state={chain.state}
        panes={chain.panes}
        onReTranslate={handleReTranslate}
        onRetryBacktest={chain.retryBacktest}
      />
      <AnalyticsAccordion translate={translate} />
    </main>
  );
}
```

- [ ] **Step 2: Fill the TODOs**

Before final tsc + commit, READ the OLD `(dashboard)/alpha/page.tsx` to extract:
1. The REAL `FACTOR_EXAMPLES` constant (the 6-item array above is placeholder copy; the real one has more curated text).
2. The REAL history-loading mechanism (likely a useEffect calling a `/api/alpha/history` endpoint, or localStorage). Reuse that code verbatim.
3. The REAL save-to-zoo function signature + endpoint path.

Replace the 3 TODO blocks with the real code. The placeholder data must NOT ship.

- [ ] **Step 3: tsc + lint + build clean**

```bash
cd frontend && npx tsc --noEmit && npx next lint && npm run build 2>&1 | tail -15
```

- [ ] **Step 4: Visual sanity (manual)**

`npm run dev` then navigate to `/alpha`. Verify:
- Empty state shows textarea + Examples chips + Universe + History dropdown + disabled TRANSLATE & BACKTEST button.
- Typing into textarea hides the chips.
- Clicking History dropdown opens popover.
- Clicking TRANSLATE & BACKTEST (with a real hypothesis) triggers the chain; verdict bar shows "Translating..." then "Backtesting...", evidence panes fill progressively.
- LOOKAHEAD.GUARD auto-expansion fires when an obvious-leak hypothesis is submitted (e.g., "next day's returns").

- [ ] **Step 5: Commit**

```bash
git add "frontend/src/app/(dashboard)/alpha/page.tsx"
git commit -m "feat(alpha): page.tsx rewritten as thin orchestrator (1632 -> ~150 lines)

The old 11-pane stateful monolith is replaced by:
  - useAlphaChain hook (state + 2-call orchestration)
  - HypothesisInputCard (input, examples, history dropdown)
  - VerdictBar (progressive stage indicator + traffic-light metrics)
  - EvidencePaneGrid (SpecPane + SmokePane + BacktestPane with progressive
    reveal + per-pane retry on soft errors)
  - AnalyticsAccordion (5 analytics panes, smart-expand on warning flags)
Decision-session mode locked; TRANSLATE & BACKTEST is the single Primary
Action; SAVE TO ZOO uses one-click + toast.success(Undo) per the brainstorm
spec (docs/superpowers/specs/2026-05-23-alpha-redesign-design.md)."
```

---

### Task 7: deploy + smoke + visual verification

- [ ] **Step 1: push**

```bash
git push
```

- [ ] **Step 2: Wait for Vercel deploy + open the frontend URL**

Open `/alpha` in the deployed frontend. Verify the same 5 visual checks from Task 6 Step 4 on the live URL. Specifically:
- Loading skeleton flashes <100ms after navigation (from Phase UX-0 loading.tsx).
- The 2-call chain works against prod backend.
- Toast on save (if save endpoint is wired) appears bottom-right per Phase UX-0 viewport placement.
- No `bg-tm-card` ghost-rendering bugs (each section has a visible bg + border).

- [ ] **Step 3: Optional polish PR**

If any prod-only issues surface (e.g., backtest endpoint shape differs from local expectation), file fix commits referencing this plan.

---

## Self-Review

**Spec coverage (all 9 brainstorm decisions):**
- 1 (mode) + 2 (auto-chain): T1 + T6 (single Primary Action, sequential 2-call chain).
- 3 (verdict bar + 3 evidence + collapsed analytics layout): T3 + T4 + T5 + T6.
- 4 (progressive reveal): T1 state machine produces 3 separate pane states; T4 evidence panes render skeleton/ok independently.
- 5 (traffic-light verdict): T1 `evalThresholds` + T3 inline marks + hover threshold strings.
- 6 (smart auto-expand): T5 `autoFlags` + conditional rendering above the toggle.
- 7 (state-gated examples + history dropdown): T2 + T6.
- 8 (one-click Save + Undo toast): T6 `handleSave` + Phase UX-0 `useToast.success` with action.
- 9 (phased degradation errors): T1 `ChainState` includes `translate_error` and `backtest_error` variants; T3 + T4 render them differently.

**Anti-pattern guardrails:**
- Silent exception: chain catches each API call into a structured ChainState variant; UI renders messages from there. No `console.error`-only.
- Token correctness: every block uses verified tokens (`tm-bg-2`, `tm-rule`, `tm-fg`, `tm-fg-2`, `tm-accent`, `tm-pos`, `tm-warn`, `tm-neg`, `tm-muted`, `tm-info`). NO `tm-card`, `tm-line`, `tm-fg-1`.
- Grep call chain (3c lesson): T2 + T6 explicitly say to GREP for the real `FACTOR_EXAMPLES` + history endpoint + save-to-zoo signature before shipping; placeholders flagged.
- Dual-entry: NOT relevant in this phase (no new HTTP endpoints).

**Placeholder scan (per writing-plans skill):**
- T6 has 3 TODO blocks (FACTOR_EXAMPLES copy / history loader / save endpoint). These are EXPLICITLY flagged as "must replace with real code from the existing page.tsx" before commit. Step 2 of T6 makes this a checkable gate.
- T5 sub-panes use `(translate as any).provenance` because the exact field path is unverified. T5 Step 1 ends with the explicit instruction to read types.ts and remove the `any` casts during implementation.

**Type / name consistency:**
- `ChainState` variant names (idle/translating/backtesting/done/translate_error/backtest_error) are referenced identically in T1, T3, T4, T6.
- `useAlphaChain` return shape (state/panes/metrics/thresholds/start/retryBacktest/reset/isLoading) consumed identically in T6.
- Pane state values ("waiting"/"loading"/"ok"/"error") consumed identically in T4 + T1.

**Out of scope:**
- Migrating other pages to the same pattern (separate plans per page).
- Mobile-specific tweaks beyond the `lg:` grid breakpoint.
- Streaming SSE for stage progress (post-MVP; current model uses client-side orchestration of 2 sequential REST calls).
- Adding a backtest results equity-curve chart (current BacktestPane shows Sharpe + DD numerically; chart is a future polish task).

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-23-alpha-redesign.md`. Two execution options:

**1. Subagent-Driven (recommended)** — fresh subagent per task with two-stage review, consistent with all prior phases.

**2. Inline Execution** — same-session batched execution.

Pick approach to proceed.
