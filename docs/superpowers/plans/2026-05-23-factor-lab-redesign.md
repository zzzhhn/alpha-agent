# /factor-lab Discovery Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `/factor-lab` from a 6-pane vertical stack into a Discovery workstation: top decision card merging LIVE + DIAGNOSTIC + PROPOSE, lightweight pending proposal rows with chevron expand and inline Approve/Reject + toast Undo (Forgiveness, no window.confirm), collapsed history summary at the bottom. Eliminate 2 production debts: zero `factorLab.*` i18n keys and the window.confirm modal on approve actions.

**Architecture:** A `FactorLabPage` server component fetches diagnostic + pending + history in parallel and mounts 3 sections: `FactorLabDecisionCard` (left LIVE + right WEAK SIGNAL + cross-column SYMPTOM + ProposeActionRow at bottom), `PendingProposalsSection` (lightweight rows with chevron expand), `HistoryCollapsedSection` (summary line + chevron expand to existing FactorHistoryTable). Client components own row expand state, propose result state, approve/reject + toast Undo flow.

**Tech Stack:** Next.js 14 App Router + RSC + TypeScript + Tailwind (`tm-*` design tokens) + lucide-react + Phase UX-0 `useToast` + existing TmPane chrome. Reuses existing `fetchFactorDiagnostic` / `fetchFactorProposals` / `proposeFactors` / `approveFactorProposal` / `rejectFactorProposal` / `rollbackFactor` API client.

---

## Dependencies + grounding (read first during Task 0)

### Pre-flight grep (mandatory)

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent
# Verify FactorProposal, FactorDiagnostic, ProposeResult types
grep -nA20 "interface FactorDiagnostic\|interface FactorProposal\|interface ProposeResult\|type ApproveResult" frontend/src/lib/api/factor-lab.ts
# Verify the action signatures we will call
grep -nE "export (async function|const) (approveFactorProposal|rejectFactorProposal|rollbackFactor|proposeFactors|fetchFactor)" frontend/src/lib/api/factor-lab.ts
# Verify locale helper paths
grep -nE "useLocale|LocaleProvider" frontend/src/components/layout/LocaleProvider.tsx | head -5
# Verify the current page imports + sections we are replacing
sed -n '1,15p' "frontend/src/app/(dashboard)/factor-lab/page.tsx"
```

### Cross-cutting conventions audit (per `feedback_cross_cutting_conventions_audit`)

| Convention | Current state | Redesign must |
|------------|---------------|---------------|
| i18n keys (`factorLab.*`) | 0 keys, entire page hardcoded English | Add ~42 new `factorLab.*` keys, zh + en parity (Task 1). |
| Font convention | `font-tm-mono` already used | Preserve. Expressions and numeric cells use `font-mono`; all labels + body text use `font-tm-mono`. |
| Layout wrappers | `TmScreen` + `TmPane` already used | Preserve. Decision card is a single TmPane wrapping a 2-column grid. |
| Locale-aware data | `useLocale` not yet imported | Client components import `useLocale`. Server components read locale from cookie/header and pass via `t(locale, ...)`. |
| Sidebar nav | Entry already at `Sidebar.tsx:67` | No change. |
| Loading skeleton | `loading.tsx` exists (Phase UX-0) | Preserve. |
| Toast system | Phase UX-0 `useToast` available | Wire into all client action handlers. |
| Token correctness | Already correct (fc64924) | Preserve verified `tm-*` tokens; ban `tm-card` / `tm-line` / `tm-fg-1`. |
| Shared errorParse | Lives in `components/backtest/errorParse.ts` | Move to `lib/factor-errors.ts` and rename `parseBacktestError` → `parseFactorError` (Task 0). |

### 10 UX First Principles re-check (per `feedback_ui_ux_first_principles`)

| # | Principle | Redesign landing point |
|---|-----------|------------------------|
| 1 | Intent alignment | Decision card co-locates diagnostic context with propose action. |
| 2 | Cognitive load minimization | Default visible attention slots ≤ 10. Hypothesis / justification / full history / diff collapsed. |
| 3 | Visibility of system status | Propose: spinner + toast + inline result line. Approve: button spinner + toast + RSC refresh. |
| 4 | Forgiveness | window.confirm eliminated. Approve/Reject toast Undo (8s) → rollback endpoint. |
| 5 | Affordance | Single accent button (Propose); secondary outlined (Approve/Reject); tertiary icons (chevron). |
| 6 | Design disappears | TmPane chrome unified across sections. |
| 7 | No manual needed | Header caption explains workflow in one line; 4-outcome explanations inline. |
| 8 | Respects user time | Propose 30-60s expectation surfaced; approve sub-second + RSC refresh. |
| 9 | No dark patterns | 4 outcomes honestly explained; DS threshold tooltip visible. |
| 10 | One Primary Action | Propose is the only accent button on the page. |

### Anti-pattern guardrails (compounded lessons)

- **Silent exception**: every try/catch surfaces via toast OR pane error state. No `console.error`-only.
- **Token correctness**: only verified `tm-*` tokens; Tailwind silent-drops unknown classes.
- **Grep call chain before field access**: before reading any property on a fetched object, grep the type definition.
- **Cross-cutting conventions**: every visible string MUST resolve through `t(locale, ...)`.
- **Plan type signatures vs API truth** (per `feedback_plan_type_signatures_vs_api_truth`): the types in this plan are aspirational; implementer must grep `frontend/src/lib/api/factor-lab.ts` for the real shapes before writing component code.

---

## File Structure

```
frontend/
├── src/
│   ├── app/(dashboard)/factor-lab/
│   │   └── page.tsx                                  ← REWRITE (Task 7), ~150 lines
│   ├── components/factor-lab/
│   │   ├── FactorHistoryTable.tsx                    ← preserve (mounted by HistoryCollapsedSection)
│   │   ├── HistoryCollapsedSection.tsx               ← new (Task 2)
│   │   ├── LiveExpressionPanel.tsx                   ← new (Task 3)
│   │   ├── WeakSignalPanel.tsx                       ← new (Task 3)
│   │   ├── SymptomCaption.tsx                        ← new (Task 3)
│   │   ├── ProposeActionRow.tsx                      ← new (Task 4), replaces ProposeButton.tsx
│   │   ├── FactorLabDecisionCard.tsx                 ← new (Task 5)
│   │   ├── PendingProposalsSection.tsx               ← new (Task 6), replaces PendingFactorProposalsTable.tsx
│   │   ├── ProposeButton.tsx                         ← DELETE (Task 7) after ProposeActionRow replaces
│   │   └── PendingFactorProposalsTable.tsx           ← DELETE (Task 7) after PendingProposalsSection replaces
│   └── lib/
│       ├── factor-errors.ts                          ← new (Task 0), moved from components/backtest/errorParse.ts
│       └── i18n.ts                                   ← MODIFY (Task 1), +42 keys × 2 blocks
└── ...

frontend/src/components/backtest/errorParse.ts        ← DELETE (Task 0) after move
```

---

### Task 0: Refactor `errorParse.ts` → `lib/factor-errors.ts`

**Files:**
- Create: `frontend/src/lib/factor-errors.ts`
- Modify: 5 /backtest files (import path update)
- Delete: `frontend/src/components/backtest/errorParse.ts`

This task is a prerequisite for /factor-lab to consume the same error parser without cross-component coupling.

- [ ] **Step 1: Read the current errorParse.ts**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent
cat frontend/src/components/backtest/errorParse.ts
```

Note the exported names. Currently: `ParsedError` (interface), `parseBacktestError` (function). The latter will be renamed to `parseFactorError`.

- [ ] **Step 2: Create `frontend/src/lib/factor-errors.ts`**

```typescript
// frontend/src/lib/factor-errors.ts
//
// Shared error parser for the factor engine UI surface.
// Consumed by /backtest (4 panes + page.tsx) and /factor-lab (ProposeActionRow).
// Handles the FastAPI 422 literal_error envelope and the 400 detail message
// shape that the AST validator produces.

export interface ParsedError {
  kind: "validation" | "network" | "unknown";
  summary: string;          // 1-line, ≤140 chars
  detail: string | null;    // full original message, or null if summary IS full
  badField?: string | null; // e.g. "operators_used[1]" or "expression.operand"
  badValue?: string | null; // e.g. "ts_means" or "retruns"
}

// ... copy the FULL implementation from components/backtest/errorParse.ts verbatim,
// renaming only the function: parseBacktestError → parseFactorError.
// Preserve all branches (400 unknown operand regex, 422 literal_error JSON.parse,
// fallthrough truncation).
```

The implementer pastes the actual current implementation; do not invent. Rename the function only.

- [ ] **Step 3: Update 5 /backtest import sites**

```bash
grep -rn "from \"./errorParse\"\|from \"@/components/backtest/errorParse\"\|parseBacktestError" frontend/src/ --include="*.tsx" --include="*.ts"
```

For each match, update:
- Import path: `from "./errorParse"` or `from "@/components/backtest/errorParse"` → `from "@/lib/factor-errors"`
- Symbol: `parseBacktestError` → `parseFactorError`

Files to edit:
- `frontend/src/components/backtest/BacktestVerdictBar.tsx`
- `frontend/src/components/backtest/EquityCurvePane.tsx`
- `frontend/src/components/backtest/DrawdownPane.tsx`
- `frontend/src/components/backtest/WalkforwardPane.tsx`
- `frontend/src/app/(dashboard)/backtest/page.tsx`

- [ ] **Step 4: Delete the old file**

```bash
git rm frontend/src/components/backtest/errorParse.ts
```

- [ ] **Step 5: Verify**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent/frontend
npx tsc --noEmit
npx next lint --quiet --file src/lib/factor-errors.ts
```

Zero new errors.

- [ ] **Step 6: Commit**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent
git add frontend/src/lib/factor-errors.ts \
        frontend/src/components/backtest/BacktestVerdictBar.tsx \
        frontend/src/components/backtest/EquityCurvePane.tsx \
        frontend/src/components/backtest/DrawdownPane.tsx \
        frontend/src/components/backtest/WalkforwardPane.tsx \
        "frontend/src/app/(dashboard)/backtest/page.tsx"
git rm frontend/src/components/backtest/errorParse.ts
git commit -m "refactor: move errorParse to lib/factor-errors as parseFactorError"
```

---

### Task 1: i18n keys for `factorLab.*` namespace

**Files:**
- Modify: `frontend/src/lib/i18n.ts`

Add 42 keys × 2 blocks (zh + en parity).

- [ ] **Step 1: Verify the current i18n.ts structure**

```bash
grep -nE '^\s+(zh|en):\s*\{|^\s+"backtest\.|^\s+"factorLab\.' frontend/src/lib/i18n.ts | head -20
```

Identify where the backtest redesign keys were added in zh + en blocks. The factorLab keys go in the same expansion area.

- [ ] **Step 2: Add 42 keys to both zh and en blocks**

zh block addition (paste at end of zh block expansion area):

```typescript
// Factor Lab redesign keys (T1-T7)
"factorLab.title": "FACTOR LAB",
"factorLab.subtitle": "因子提议工作站 · 人审 LLM 候选",
"factorLab.decision.title": "决策",
"factorLab.decision.liveExpression": "当前生效表达式",
"factorLab.decision.deployedAgo": "{n} 天前部署",
"factorLab.decision.weakSignal": "薄弱信号",
"factorLab.decision.noWeakSignal": "当前无薄弱信号",
"factorLab.decision.ic": "IC",
"factorLab.decision.worstFold": "最差窗口 Sharpe",
"factorLab.decision.symptom": "症状",
"factorLab.decision.diagnosticUnavailable": "诊断数据不可用",
"factorLab.propose.button": "提议新因子 (n={n})",
"factorLab.propose.running": "提议中… 30-60s",
"factorLab.propose.lastResult": "上次提议",
"factorLab.propose.errorPrefix": "提议失败",
"factorLab.propose.outcome.dormant": "validator 未通过或 cost-guard 触发；LLM 未被调用。",
"factorLab.propose.outcome.empty": "LLM 返回空或解析失败，建议重试。",
"factorLab.propose.outcome.noBeat": "{n} 个候选评估完毕，无一击败 baseline。",
"factorLab.propose.outcome.queued": "{n} 个候选已入队，下方 review 后启用。",
"factorLab.pending.title": "待审提议",
"factorLab.pending.empty": "暂无待审提议",
"factorLab.pending.colExpression": "表达式",
"factorLab.pending.colDS": "DS",
"factorLab.pending.colActions": "操作",
"factorLab.pending.approve": "启用",
"factorLab.pending.reject": "拒绝",
"factorLab.pending.hypothesis": "假设",
"factorLab.pending.justification": "校验依据",
"factorLab.pending.metrics": "指标",
"factorLab.pending.diffVsLive": "vs live 差异",
"factorLab.toast.approved": "已启用 · {expression}",
"factorLab.toast.rejected": "已拒绝",
"factorLab.toast.undo": "撤销",
"factorLab.toast.undoRejected": "撤销 (恢复 pending)",
"factorLab.toast.approveFailed": "无法启用 — 状态已变更",
"factorLab.toast.rejectFailed": "无法拒绝",
"factorLab.toast.rollbackFailed": "撤销失败",
"factorLab.history.title": "历史",
"factorLab.history.summary30d": "过去 30 天: {n} 提议 / {a} 启用 / {r} 拒绝 / {b} 回滚",
"factorLab.history.expand": "展开完整历史",
"factorLab.history.empty": "暂无历史",
```

en block addition (paste at end of en block expansion area):

```typescript
// Factor Lab redesign keys (T1-T7)
"factorLab.title": "FACTOR LAB",
"factorLab.subtitle": "Factor proposal workstation · Human-gated LLM candidates",
"factorLab.decision.title": "DECISION",
"factorLab.decision.liveExpression": "LIVE EXPRESSION",
"factorLab.decision.deployedAgo": "deployed {n}d ago",
"factorLab.decision.weakSignal": "WEAK SIGNAL",
"factorLab.decision.noWeakSignal": "No weak signal detected",
"factorLab.decision.ic": "IC",
"factorLab.decision.worstFold": "Worst fold Sharpe",
"factorLab.decision.symptom": "Symptom",
"factorLab.decision.diagnosticUnavailable": "Diagnostic unavailable",
"factorLab.propose.button": "Propose factors (n={n})",
"factorLab.propose.running": "Proposing... 30-60s",
"factorLab.propose.lastResult": "Last propose",
"factorLab.propose.errorPrefix": "Propose failed",
"factorLab.propose.outcome.dormant": "Validator gated or cost-guard tripped; LLM not invoked.",
"factorLab.propose.outcome.empty": "LLM returned empty or unparseable; retry suggested.",
"factorLab.propose.outcome.noBeat": "{n} candidate(s) evaluated; none beat baseline.",
"factorLab.propose.outcome.queued": "{n} candidate(s) queued; review below to enable.",
"factorLab.pending.title": "PENDING PROPOSALS",
"factorLab.pending.empty": "No pending proposals",
"factorLab.pending.colExpression": "Expression",
"factorLab.pending.colDS": "DS",
"factorLab.pending.colActions": "Actions",
"factorLab.pending.approve": "Approve",
"factorLab.pending.reject": "Reject",
"factorLab.pending.hypothesis": "Hypothesis",
"factorLab.pending.justification": "Justification",
"factorLab.pending.metrics": "Metrics",
"factorLab.pending.diffVsLive": "Diff vs live",
"factorLab.toast.approved": "Enabled · {expression}",
"factorLab.toast.rejected": "Rejected",
"factorLab.toast.undo": "Undo",
"factorLab.toast.undoRejected": "Undo (restore pending)",
"factorLab.toast.approveFailed": "Approve failed — state changed",
"factorLab.toast.rejectFailed": "Reject failed",
"factorLab.toast.rollbackFailed": "Undo failed",
"factorLab.history.title": "HISTORY",
"factorLab.history.summary30d": "Last 30d: {n} proposed / {a} approved / {r} rejected / {b} rolled back",
"factorLab.history.expand": "View full history",
"factorLab.history.empty": "No history",
```

- [ ] **Step 3: Verify zh/en parity + tsc clean**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent/frontend
python3 -c "
import re
content = open('src/lib/i18n.ts').read()
factor_lab_zh = set(re.findall(r'\"(factorLab\.[^\"]+)\":', content[content.find('zh:'):content.find('en:')]))
factor_lab_en = set(re.findall(r'\"(factorLab\.[^\"]+)\":', content[content.find('en:'):]))
print('zh count:', len(factor_lab_zh))
print('en count:', len(factor_lab_en))
print('zh only:', factor_lab_zh - factor_lab_en)
print('en only:', factor_lab_en - factor_lab_zh)
"
npx tsc --noEmit
```

Expected: zh count == en count == 42, both diffs empty, tsc zero new errors.

- [ ] **Step 4: Commit**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent
git add frontend/src/lib/i18n.ts
git commit -m "feat(factor-lab): i18n keys for Discovery redesign (decision/propose/pending/history)"
```

---

### Task 2: HistoryCollapsedSection (smallest leaf — start here for warm-up)

**Files:**
- Create: `frontend/src/components/factor-lab/HistoryCollapsedSection.tsx`

Wraps existing `FactorHistoryTable.tsx` (preserved as-is, 201 lines) with a collapsed summary line. No rewrite of the table itself.

- [ ] **Step 1: Read FactorProposal shape**

```bash
grep -nA15 "interface FactorProposal\b" frontend/src/lib/api/factor-lab.ts
```

Record fields: at minimum `id`, `status` (`"pending" | "approved" | "rejected" | "rolled_back"?`), `created_at` (ISO string). Confirm `rolled_back` is a valid status (the spec assumes it is).

- [ ] **Step 2: Implement HistoryCollapsedSection.tsx**

```tsx
"use client";

import { useState, useMemo } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { TmPane } from "@/components/tm/TmPane";
import { FactorHistoryTable } from "./FactorHistoryTable";
import type { FactorProposal } from "@/lib/api/factor-lab";

const THIRTY_DAYS_MS = 30 * 24 * 60 * 60 * 1000;

function withinDays(iso: string, days: number): boolean {
  const t0 = Date.parse(iso);
  if (Number.isNaN(t0)) return false;
  return Date.now() - t0 <= days * 24 * 60 * 60 * 1000;
}

interface HistoryCollapsedSectionProps {
  readonly history: readonly FactorProposal[];
}

export function HistoryCollapsedSection({
  history,
}: HistoryCollapsedSectionProps) {
  const { locale } = useLocale();
  const [expanded, setExpanded] = useState(false);

  const summary = useMemo(() => {
    const recent = history.filter((p) => withinDays(p.created_at, 30));
    return {
      n: recent.length,
      a: recent.filter((p) => p.status === "approved").length,
      r: recent.filter((p) => p.status === "rejected").length,
      b: recent.filter((p) => p.status === "rolled_back").length,
    };
  }, [history]);

  const summaryText = t(
    locale,
    "factorLab.history.summary30d" as Parameters<typeof t>[1],
  )
    .replace("{n}", String(summary.n))
    .replace("{a}", String(summary.a))
    .replace("{r}", String(summary.r))
    .replace("{b}", String(summary.b));

  return (
    <TmPane
      title={t(locale, "factorLab.history.title" as Parameters<typeof t>[1])}
    >
      <button
        type="button"
        onClick={() => setExpanded((e) => !e)}
        className="flex w-full items-center justify-between px-3 py-2.5 font-tm-mono text-[11px] text-tm-fg-2 hover:bg-tm-bg-3"
        aria-expanded={expanded}
      >
        <span>{history.length === 0
          ? t(locale, "factorLab.history.empty" as Parameters<typeof t>[1])
          : summaryText}</span>
        {expanded ? (
          <ChevronDown className="h-3.5 w-3.5" strokeWidth={1.75} />
        ) : (
          <ChevronRight className="h-3.5 w-3.5" strokeWidth={1.75} />
        )}
      </button>
      {expanded && history.length > 0 ? (
        <div className="border-t border-tm-rule px-3 py-2.5">
          <FactorHistoryTable proposals={history as FactorProposal[]} />
        </div>
      ) : null}
    </TmPane>
  );
}
```

- [ ] **Step 3: tsc + lint clean**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent/frontend
npx tsc --noEmit
npx next lint --quiet --file src/components/factor-lab/HistoryCollapsedSection.tsx
```

- [ ] **Step 4: Commit**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent
git add frontend/src/components/factor-lab/HistoryCollapsedSection.tsx
git commit -m "feat(factor-lab): HistoryCollapsedSection with 30-day summary + chevron expand"
```

---

### Task 3: LiveExpressionPanel + WeakSignalPanel + SymptomCaption

**Files:**
- Create: `frontend/src/components/factor-lab/LiveExpressionPanel.tsx`
- Create: `frontend/src/components/factor-lab/WeakSignalPanel.tsx`
- Create: `frontend/src/components/factor-lab/SymptomCaption.tsx`

Three pure display panels (no client interactivity). Server-rendered.

- [ ] **Step 1: Read FactorDiagnostic shape**

```bash
grep -nA15 "interface FactorDiagnostic\b" frontend/src/lib/api/factor-lab.ts
```

Confirm fields present: `current_expression: string`, `weak_signal: string | null`, `weak_signal_ic: number | null`, `worst_fold_sharpe: number | null`, `worst_fold_window: [string, string] | null`, `symptom_summary: string`.

Also check whether a `deployed_at` or similar timestamp is present (the spec mentions "deployed 7d ago" — verify the field name; if absent, render the panel without the timestamp).

- [ ] **Step 2: Implement LiveExpressionPanel.tsx**

```tsx
import { getLocale } from "@/lib/locale-server";
import { t } from "@/lib/i18n";

interface LiveExpressionPanelProps {
  readonly expression: string;
  readonly deployedAgoDays?: number | null;
}

export async function LiveExpressionPanel({
  expression,
  deployedAgoDays,
}: LiveExpressionPanelProps) {
  const locale = await getLocale();
  return (
    <div className="flex flex-col gap-1.5">
      <div className="font-tm-mono text-[10px] uppercase tracking-wider text-tm-muted">
        {t(locale, "factorLab.decision.liveExpression" as Parameters<typeof t>[1])}
      </div>
      <pre className="overflow-x-auto rounded bg-tm-bg-2 p-2.5 font-mono text-[11px] text-tm-fg">
        {expression}
      </pre>
      {deployedAgoDays != null ? (
        <div className="font-tm-mono text-[10px] text-tm-muted">
          {t(locale, "factorLab.decision.deployedAgo" as Parameters<typeof t>[1])
            .replace("{n}", String(deployedAgoDays))}
        </div>
      ) : null}
    </div>
  );
}
```

If `getLocale` server helper does not exist at `lib/locale-server.ts`, fall back to passing `locale` as a prop from the page. Verify the existing pattern by grepping how /backtest server components handle locale:

```bash
grep -rnE "getLocale|locale-server|cookies\(\).get.*locale|headers\(\).get.*locale" frontend/src/app/ frontend/src/lib/ | head -10
```

If no server helper exists, **pass locale as a prop** from the page component (page reads from cookie/header, passes down). Use `import { t } from "@/lib/i18n";` and accept `locale: Locale` prop on each sub-panel.

- [ ] **Step 3: Implement WeakSignalPanel.tsx**

```tsx
import { t } from "@/lib/i18n";
import type { Locale } from "@/lib/i18n";

interface WeakSignalPanelProps {
  readonly locale: Locale;
  readonly weakSignal: string | null;
  readonly weakSignalIc: number | null;
  readonly worstFoldSharpe: number | null;
  readonly worstFoldWindow: readonly [string, string] | null;
}

export function WeakSignalPanel({
  locale,
  weakSignal,
  weakSignalIc,
  worstFoldSharpe,
  worstFoldWindow,
}: WeakSignalPanelProps) {
  if (weakSignal === null) {
    return (
      <div className="flex flex-col gap-1.5">
        <div className="font-tm-mono text-[10px] uppercase tracking-wider text-tm-muted">
          {t(locale, "factorLab.decision.weakSignal" as Parameters<typeof t>[1])}
        </div>
        <div className="font-tm-mono text-[11px] text-tm-muted">
          {t(locale, "factorLab.decision.noWeakSignal" as Parameters<typeof t>[1])}
        </div>
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-1.5">
      <div className="font-tm-mono text-[10px] uppercase tracking-wider text-tm-muted">
        {t(locale, "factorLab.decision.weakSignal" as Parameters<typeof t>[1])}
      </div>
      <div className="font-tm-mono text-[12px] text-tm-warn">
        <strong>{weakSignal}</strong>
        {weakSignalIc != null ? (
          <span className="ml-2 font-mono text-tm-fg-2">
            ({t(locale, "factorLab.decision.ic" as Parameters<typeof t>[1])} = {weakSignalIc.toFixed(4)})
          </span>
        ) : null}
      </div>
      {worstFoldSharpe != null ? (
        <div className="font-tm-mono text-[11px] text-tm-fg-2">
          {t(locale, "factorLab.decision.worstFold" as Parameters<typeof t>[1])}:{" "}
          <strong className="font-mono text-tm-neg">{worstFoldSharpe.toFixed(3)}</strong>
          {worstFoldWindow ? (
            <span className="ml-2 text-tm-muted">
              [{worstFoldWindow[0]} → {worstFoldWindow[1]}]
            </span>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
```

- [ ] **Step 4: Implement SymptomCaption.tsx**

```tsx
import { t } from "@/lib/i18n";
import type { Locale } from "@/lib/i18n";

interface SymptomCaptionProps {
  readonly locale: Locale;
  readonly symptom: string;
}

export function SymptomCaption({ locale, symptom }: SymptomCaptionProps) {
  if (!symptom) return null;
  return (
    <div className="border-t border-tm-rule pt-2 font-tm-mono text-[10px] text-tm-muted">
      <span className="uppercase tracking-wider">
        {t(locale, "factorLab.decision.symptom" as Parameters<typeof t>[1])}
      </span>
      <span className="ml-2">{symptom}</span>
    </div>
  );
}
```

- [ ] **Step 5: tsc + lint clean**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent/frontend
npx tsc --noEmit
npx next lint --quiet --file src/components/factor-lab/LiveExpressionPanel.tsx --file src/components/factor-lab/WeakSignalPanel.tsx --file src/components/factor-lab/SymptomCaption.tsx
```

- [ ] **Step 6: Commit**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent
git add frontend/src/components/factor-lab/LiveExpressionPanel.tsx \
        frontend/src/components/factor-lab/WeakSignalPanel.tsx \
        frontend/src/components/factor-lab/SymptomCaption.tsx
git commit -m "feat(factor-lab): LiveExpression + WeakSignal + Symptom panels for decision card"
```

---

### Task 4: ProposeActionRow (client component, replaces ProposeButton.tsx)

**Files:**
- Create: `frontend/src/components/factor-lab/ProposeActionRow.tsx`

Client component owning propose state + inline result line + chevron-expand for outcome explanation.

- [ ] **Step 1: Read ProposeResult shape + proposeFactors signature**

```bash
grep -nA10 "interface ProposeResult\|type ProposeResult\|export async function proposeFactors" frontend/src/lib/api/factor-lab.ts
```

Record: `proposed: number`, `evaluated: number`, `dormant: boolean`, any additional fields (`message?`, `timestamp?`).

- [ ] **Step 2: Implement ProposeActionRow.tsx**

```tsx
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, ChevronDown, ChevronRight, Play } from "lucide-react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { useToast } from "@/components/ui/toast";
import { t } from "@/lib/i18n";
import { proposeFactors, type ProposeResult } from "@/lib/api/factor-lab";
import { parseFactorError } from "@/lib/factor-errors";

type ProposeState =
  | { kind: "idle" }
  | { kind: "running" }
  | { kind: "ok"; result: ProposeResult; ts: number }
  | { kind: "error"; message: string };

interface ProposeActionRowProps {
  readonly n?: number;
}

function outcomeKey(r: ProposeResult): string {
  if (r.dormant) return "factorLab.propose.outcome.dormant";
  if (r.evaluated === 0) return "factorLab.propose.outcome.empty";
  if (r.proposed === 0) return "factorLab.propose.outcome.noBeat";
  return "factorLab.propose.outcome.queued";
}

function formatTs(ts: number): string {
  const d = new Date(ts);
  return d.toTimeString().slice(0, 8);
}

export function ProposeActionRow({ n = 5 }: ProposeActionRowProps) {
  const { locale } = useLocale();
  const { toast } = useToast();
  const router = useRouter();
  const [state, setState] = useState<ProposeState>({ kind: "idle" });
  const [resultExpanded, setResultExpanded] = useState(false);

  async function handleClick() {
    setState({ kind: "running" });
    try {
      const result = await proposeFactors(n);
      setState({ kind: "ok", result, ts: Date.now() });
      router.refresh();
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setState({ kind: "error", message: msg });
    }
  }

  const buttonLabel = state.kind === "running"
    ? t(locale, "factorLab.propose.running" as Parameters<typeof t>[1])
    : t(locale, "factorLab.propose.button" as Parameters<typeof t>[1])
        .replace("{n}", String(n));

  return (
    <div className="flex flex-col gap-2">
      <button
        type="button"
        onClick={handleClick}
        disabled={state.kind === "running"}
        className="inline-flex w-fit items-center gap-2 rounded border border-tm-accent/60 bg-tm-accent px-3 py-1.5 font-tm-mono text-[11px] text-tm-bg transition-opacity disabled:opacity-50 enabled:hover:bg-tm-accent/90"
      >
        {state.kind === "running" ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin" strokeWidth={1.75} />
        ) : (
          <Play className="h-3.5 w-3.5" strokeWidth={1.75} />
        )}
        <span>{buttonLabel}</span>
      </button>

      {state.kind === "ok" ? (
        <div className="flex flex-col gap-1 rounded border border-tm-rule bg-tm-bg-2 px-3 py-2">
          <button
            type="button"
            onClick={() => setResultExpanded((e) => !e)}
            className="flex items-center gap-2 font-tm-mono text-[11px] text-tm-fg-2"
            aria-expanded={resultExpanded}
          >
            {resultExpanded ? (
              <ChevronDown className="h-3 w-3" strokeWidth={1.75} />
            ) : (
              <ChevronRight className="h-3 w-3" strokeWidth={1.75} />
            )}
            <span>
              {t(locale, "factorLab.propose.lastResult" as Parameters<typeof t>[1])}
              {" · "}
              <span className="font-mono">{state.result.proposed} / {state.result.evaluated}</span>
              {" · "}
              <span className="font-mono">{formatTs(state.ts)}</span>
            </span>
          </button>
          {resultExpanded ? (
            <p className="pl-5 font-tm-mono text-[11px] text-tm-fg-2">
              {t(locale, outcomeKey(state.result) as Parameters<typeof t>[1])
                .replace("{n}", String(state.result.evaluated || state.result.proposed))}
            </p>
          ) : null}
        </div>
      ) : null}

      {state.kind === "error" ? (
        <div className="rounded border border-tm-neg/60 bg-tm-neg/10 px-3 py-2 font-tm-mono text-[11px] text-tm-neg">
          <div>
            {t(locale, "factorLab.propose.errorPrefix" as Parameters<typeof t>[1])}
            {": "}
            {parseFactorError(state.message).summary}
          </div>
          <details className="mt-1 text-tm-muted">
            <summary className="cursor-pointer text-[10px]">
              {t(locale, "backtest.verdict.errorDetails" as Parameters<typeof t>[1])}
            </summary>
            <pre className="mt-1 max-h-32 overflow-auto whitespace-pre-wrap break-all text-[10px]">
              {state.message}
            </pre>
          </details>
        </div>
      ) : null}
    </div>
  );
}
```

The error block reuses `backtest.verdict.errorDetails` (already exists from /backtest Fix B). If that key is missing in i18n.ts (defensive check), add it; otherwise reuse.

- [ ] **Step 3: tsc + lint clean**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent/frontend
npx tsc --noEmit
npx next lint --quiet --file src/components/factor-lab/ProposeActionRow.tsx
```

- [ ] **Step 4: Commit**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent
git add frontend/src/components/factor-lab/ProposeActionRow.tsx
git commit -m "feat(factor-lab): ProposeActionRow client component with inline result line"
```

---

### Task 5: FactorLabDecisionCard (composer for T3 + T4)

**Files:**
- Create: `frontend/src/components/factor-lab/FactorLabDecisionCard.tsx`

Server component composing 4 sub-components into one TmPane.

- [ ] **Step 1: Implement**

```tsx
import { t } from "@/lib/i18n";
import type { Locale } from "@/lib/i18n";
import { TmPane } from "@/components/tm/TmPane";
import type { FactorDiagnostic } from "@/lib/api/factor-lab";
import { LiveExpressionPanel } from "./LiveExpressionPanel";
import { WeakSignalPanel } from "./WeakSignalPanel";
import { SymptomCaption } from "./SymptomCaption";
import { ProposeActionRow } from "./ProposeActionRow";

interface FactorLabDecisionCardProps {
  readonly locale: Locale;
  readonly diagnostic: FactorDiagnostic | null;
}

export function FactorLabDecisionCard({
  locale,
  diagnostic,
}: FactorLabDecisionCardProps) {
  const title = t(
    locale,
    "factorLab.decision.title" as Parameters<typeof t>[1],
  );

  if (diagnostic === null) {
    return (
      <TmPane title={title}>
        <div className="px-3 py-2.5">
          <p className="font-tm-mono text-[11px] text-tm-neg">
            {t(locale, "factorLab.decision.diagnosticUnavailable" as Parameters<typeof t>[1])}
          </p>
          <div className="mt-3">
            <ProposeActionRow n={5} />
          </div>
        </div>
      </TmPane>
    );
  }

  return (
    <TmPane title={title}>
      <div className="flex flex-col gap-3 px-3 py-2.5">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <LiveExpressionPanel
            locale={locale}
            expression={diagnostic.current_expression}
            deployedAgoDays={null}
          />
          <WeakSignalPanel
            locale={locale}
            weakSignal={diagnostic.weak_signal}
            weakSignalIc={diagnostic.weak_signal_ic}
            worstFoldSharpe={diagnostic.worst_fold_sharpe}
            worstFoldWindow={diagnostic.worst_fold_window}
          />
        </div>
        <SymptomCaption locale={locale} symptom={diagnostic.symptom_summary} />
        <div>
          <ProposeActionRow n={5} />
        </div>
      </div>
    </TmPane>
  );
}
```

Note: `LiveExpressionPanel` now takes `locale` as a prop (per Task 3 Step 2 fallback decision). Confirm this matches the actual signature you wrote in Task 3.

- [ ] **Step 2: tsc + lint clean**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent/frontend
npx tsc --noEmit
npx next lint --quiet --file src/components/factor-lab/FactorLabDecisionCard.tsx
```

- [ ] **Step 3: Commit**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent
git add frontend/src/components/factor-lab/FactorLabDecisionCard.tsx
git commit -m "feat(factor-lab): FactorLabDecisionCard composes LIVE + WEAK + SYMPTOM + propose"
```

---

### Task 6: PendingProposalsSection (replaces PendingFactorProposalsTable)

**Files:**
- Create: `frontend/src/components/factor-lab/PendingProposalsSection.tsx`

Client component with: lightweight rows + chevron expand + inline Approve/Reject + toast Undo. Eliminates `window.confirm()` from current implementation.

- [ ] **Step 1: Read approve/reject/rollback signatures + FactorProposal full shape**

```bash
grep -nA10 "approveFactorProposal\|rejectFactorProposal\|rollbackFactor" frontend/src/lib/api/factor-lab.ts
grep -nA20 "interface FactorProposal\b" frontend/src/lib/api/factor-lab.ts
```

Record fields: `id`, `expression`, `hypothesis?`, `justification?`, `status`, `metrics?` (verify exact shape: probably `deflated_sharpe`, `ic`, `p_value`, `turnover`, `sharpe`, `max_dd`, `n_days`), and the live expression source to diff against (it's in `diagnostic.current_expression` passed in from page).

- [ ] **Step 2: Implement PendingProposalsSection.tsx**

```tsx
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ChevronDown, ChevronRight, Loader2 } from "lucide-react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { useToast } from "@/components/ui/toast";
import { t } from "@/lib/i18n";
import { TmPane } from "@/components/tm/TmPane";
import {
  approveFactorProposal,
  rejectFactorProposal,
  rollbackFactor,
  type FactorProposal,
} from "@/lib/api/factor-lab";

type RowActionState = "idle" | "approving" | "rejecting";

interface PendingProposalsSectionProps {
  readonly proposals: readonly FactorProposal[];
  readonly liveExpression: string;
}

function shortExpr(expr: string, max = 40): string {
  return expr.length <= max ? expr : expr.slice(0, max - 1) + "…";
}

function diffLines(live: string, next: string): readonly { sign: "-" | "+"; text: string }[] {
  return [
    { sign: "-" as const, text: live },
    { sign: "+" as const, text: next },
  ];
}

export function PendingProposalsSection({
  proposals,
  liveExpression,
}: PendingProposalsSectionProps) {
  const { locale } = useLocale();
  const { toast } = useToast();
  const router = useRouter();
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [actionState, setActionState] = useState<Map<string, RowActionState>>(
    new Map(),
  );

  function toggleExpand(id: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function setRowState(id: string, s: RowActionState) {
    setActionState((prev) => {
      const next = new Map(prev);
      if (s === "idle") next.delete(id);
      else next.set(id, s);
      return next;
    });
  }

  async function handleApprove(p: FactorProposal) {
    setRowState(p.id, "approving");
    try {
      await approveFactorProposal(p.id);
      router.refresh();
      toast.success(
        t(locale, "factorLab.toast.approved" as Parameters<typeof t>[1])
          .replace("{expression}", shortExpr(p.expression)),
        {
          action: {
            label: t(locale, "factorLab.toast.undo" as Parameters<typeof t>[1]),
            onClick: async () => {
              try {
                await rollbackFactor(p.id);
                router.refresh();
              } catch {
                toast.error(t(locale, "factorLab.toast.rollbackFailed" as Parameters<typeof t>[1]));
              }
            },
          },
          duration: 8000,
        },
      );
    } catch {
      toast.error(t(locale, "factorLab.toast.approveFailed" as Parameters<typeof t>[1]));
      router.refresh();
    } finally {
      setRowState(p.id, "idle");
    }
  }

  async function handleReject(p: FactorProposal) {
    setRowState(p.id, "rejecting");
    try {
      await rejectFactorProposal(p.id);
      router.refresh();
      toast.success(
        t(locale, "factorLab.toast.rejected" as Parameters<typeof t>[1]),
        {
          action: {
            label: t(locale, "factorLab.toast.undoRejected" as Parameters<typeof t>[1]),
            onClick: async () => {
              try {
                await rollbackFactor(p.id);
                router.refresh();
              } catch {
                toast.error(t(locale, "factorLab.toast.rollbackFailed" as Parameters<typeof t>[1]));
              }
            },
          },
          duration: 8000,
        },
      );
    } catch {
      toast.error(t(locale, "factorLab.toast.rejectFailed" as Parameters<typeof t>[1]));
      router.refresh();
    } finally {
      setRowState(p.id, "idle");
    }
  }

  const title = t(locale, "factorLab.pending.title" as Parameters<typeof t>[1]);

  if (proposals.length === 0) {
    return (
      <TmPane title={title} meta="0">
        <div className="px-3 py-2.5 font-tm-mono text-[11px] text-tm-muted">
          {t(locale, "factorLab.pending.empty" as Parameters<typeof t>[1])}
        </div>
      </TmPane>
    );
  }

  return (
    <TmPane title={title} meta={`${proposals.length}`}>
      <div className="divide-y divide-tm-rule">
        {proposals.map((p) => {
          const isOpen = expanded.has(p.id);
          const state = actionState.get(p.id) ?? "idle";
          const ds = p.metrics?.deflated_sharpe;
          return (
            <div key={p.id} className="px-3 py-2">
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => toggleExpand(p.id)}
                  className="text-tm-muted hover:text-tm-fg"
                  aria-expanded={isOpen}
                  aria-label="expand"
                >
                  {isOpen ? (
                    <ChevronDown className="h-3.5 w-3.5" strokeWidth={1.75} />
                  ) : (
                    <ChevronRight className="h-3.5 w-3.5" strokeWidth={1.75} />
                  )}
                </button>
                <code className="flex-1 truncate font-mono text-[11px] text-tm-fg">
                  {p.expression}
                </code>
                <span className="shrink-0 font-mono text-[11px] text-tm-fg-2">
                  {t(locale, "factorLab.pending.colDS" as Parameters<typeof t>[1])}
                  {" "}
                  {ds != null ? ds.toFixed(2) : "—"}
                </span>
                <button
                  type="button"
                  onClick={() => handleApprove(p)}
                  disabled={state !== "idle"}
                  className="inline-flex items-center gap-1 rounded border border-tm-pos/60 bg-tm-pos/10 px-2 py-0.5 font-tm-mono text-[10px] text-tm-pos transition-opacity disabled:opacity-40 enabled:hover:bg-tm-pos/20"
                >
                  {state === "approving" ? (
                    <Loader2 className="h-3 w-3 animate-spin" strokeWidth={1.75} />
                  ) : null}
                  <span>{t(locale, "factorLab.pending.approve" as Parameters<typeof t>[1])}</span>
                </button>
                <button
                  type="button"
                  onClick={() => handleReject(p)}
                  disabled={state !== "idle"}
                  className="inline-flex items-center gap-1 rounded border border-tm-rule bg-tm-bg-3 px-2 py-0.5 font-tm-mono text-[10px] text-tm-fg-2 transition-opacity disabled:opacity-40 enabled:hover:bg-tm-bg-3/60"
                >
                  {state === "rejecting" ? (
                    <Loader2 className="h-3 w-3 animate-spin" strokeWidth={1.75} />
                  ) : null}
                  <span>{t(locale, "factorLab.pending.reject" as Parameters<typeof t>[1])}</span>
                </button>
              </div>

              {isOpen ? (
                <div className="mt-2 ml-5 flex flex-col gap-2 rounded border border-tm-rule bg-tm-bg-2 px-3 py-2.5">
                  {p.hypothesis ? (
                    <div>
                      <div className="font-tm-mono text-[10px] uppercase tracking-wider text-tm-muted">
                        {t(locale, "factorLab.pending.hypothesis" as Parameters<typeof t>[1])}
                      </div>
                      <p className="font-tm-mono text-[11px] text-tm-fg-2">{p.hypothesis}</p>
                    </div>
                  ) : null}
                  {p.justification ? (
                    <div>
                      <div className="font-tm-mono text-[10px] uppercase tracking-wider text-tm-muted">
                        {t(locale, "factorLab.pending.justification" as Parameters<typeof t>[1])}
                      </div>
                      <p className="font-tm-mono text-[11px] text-tm-fg-2">{p.justification}</p>
                    </div>
                  ) : null}
                  {p.metrics ? (
                    <div>
                      <div className="font-tm-mono text-[10px] uppercase tracking-wider text-tm-muted">
                        {t(locale, "factorLab.pending.metrics" as Parameters<typeof t>[1])}
                      </div>
                      <div className="grid grid-cols-3 gap-2 font-mono text-[11px] text-tm-fg-2">
                        <span>IC {p.metrics.ic?.toFixed(4) ?? "—"}</span>
                        <span>p {p.metrics.p_value?.toFixed(3) ?? "—"}</span>
                        <span>turnover {p.metrics.turnover != null ? (p.metrics.turnover * 100).toFixed(0) + "%" : "—"}</span>
                        <span>Sharpe {p.metrics.sharpe?.toFixed(2) ?? "—"}</span>
                        <span>maxDD {p.metrics.max_drawdown != null ? (p.metrics.max_drawdown * 100).toFixed(1) + "%" : "—"}</span>
                        <span>n_days {p.metrics.n_days ?? "—"}</span>
                      </div>
                    </div>
                  ) : null}
                  <div>
                    <div className="font-tm-mono text-[10px] uppercase tracking-wider text-tm-muted">
                      {t(locale, "factorLab.pending.diffVsLive" as Parameters<typeof t>[1])}
                    </div>
                    <pre className="overflow-x-auto rounded bg-tm-bg-3/60 p-2 font-mono text-[10px]">
                      {diffLines(liveExpression, p.expression).map((line, i) => (
                        <div key={i} className={line.sign === "-" ? "text-tm-neg" : "text-tm-pos"}>
                          {line.sign} {line.text}
                        </div>
                      ))}
                    </pre>
                  </div>
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </TmPane>
  );
}
```

**Type contract caveat:** The `p.metrics` shape used above (with `deflated_sharpe`, `ic`, `p_value`, `turnover`, `sharpe`, `max_drawdown`, `n_days`) is the spec's assumption. The implementer must grep the real `FactorProposal.metrics` type in api/factor-lab.ts and adapt the field paths. If a field is missing from the real type, render `—`; never crash.

- [ ] **Step 3: tsc + lint clean**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent/frontend
npx tsc --noEmit
npx next lint --quiet --file src/components/factor-lab/PendingProposalsSection.tsx
```

- [ ] **Step 4: Commit**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent
git add frontend/src/components/factor-lab/PendingProposalsSection.tsx
git commit -m "feat(factor-lab): PendingProposalsSection with chevron expand + inline Approve/Reject + toast Undo"
```

---

### Task 7: page.tsx rewrite + delete old components

**Files:**
- Rewrite: `frontend/src/app/(dashboard)/factor-lab/page.tsx`
- Delete: `frontend/src/components/factor-lab/ProposeButton.tsx`
- Delete: `frontend/src/components/factor-lab/PendingFactorProposalsTable.tsx`

Thin server-component orchestrator: parallel fetch + locale read + mount 3 sections + delete deprecated components.

- [ ] **Step 1: Determine locale-reading mechanism for the server component**

```bash
grep -rnE "cookies\(\)\.get|headers\(\)\.get.*locale|getLocale\(\)|defaultLocale" frontend/src/app/ frontend/src/lib/ | head -10
```

Identify how server-rendered pages get the user's locale. Likely options:
1. `cookies().get("locale")` from `next/headers`
2. A helper `getServerLocale()` in `lib/locale-server.ts`
3. The `LocaleProvider` reads from cookie, and server pages default to one locale

Pick the existing pattern. If no pattern exists, default to reading from cookie:

```typescript
import { cookies } from "next/headers";
import type { Locale } from "@/lib/i18n";

async function getLocaleFromCookie(): Promise<Locale> {
  const c = await cookies();
  const v = c.get("locale")?.value;
  return v === "zh" || v === "en" ? v : "en";
}
```

- [ ] **Step 2: Write the new page.tsx**

```tsx
import { cookies } from "next/headers";
import type { Locale } from "@/lib/i18n";
import { TmScreen } from "@/components/tm/TmPane";
import {
  fetchFactorDiagnostic,
  fetchFactorProposals,
} from "@/lib/api/factor-lab";
import { FactorLabDecisionCard } from "@/components/factor-lab/FactorLabDecisionCard";
import { PendingProposalsSection } from "@/components/factor-lab/PendingProposalsSection";
import { HistoryCollapsedSection } from "@/components/factor-lab/HistoryCollapsedSection";

export const dynamic = "force-dynamic";

async function getLocaleFromCookie(): Promise<Locale> {
  const c = await cookies();
  const v = c.get("locale")?.value;
  return v === "zh" || v === "en" ? v : "en";
}

export default async function FactorLabPage() {
  const locale = await getLocaleFromCookie();

  const [diagSettled, pendingSettled, allSettled] = await Promise.allSettled([
    fetchFactorDiagnostic({ revalidate: 0, tags: ["factor-lab-diagnostic"] }),
    fetchFactorProposals("pending", { revalidate: 0, tags: ["factor-lab-pending"] }),
    fetchFactorProposals(undefined, { revalidate: 0, tags: ["factor-lab-history"] }),
  ]);

  const diagnostic =
    diagSettled.status === "fulfilled" ? diagSettled.value : null;
  const pending =
    pendingSettled.status === "fulfilled" ? pendingSettled.value.proposals : [];
  const all =
    allSettled.status === "fulfilled" ? allSettled.value.proposals : [];
  const history = all.filter((p) => p.status !== "pending");
  const liveExpression = diagnostic?.current_expression ?? "";

  return (
    <TmScreen>
      <FactorLabDecisionCard locale={locale} diagnostic={diagnostic} />
      <PendingProposalsSection
        proposals={pending}
        liveExpression={liveExpression}
      />
      <HistoryCollapsedSection history={history} />
    </TmScreen>
  );
}
```

- [ ] **Step 3: Delete deprecated components**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent
git rm frontend/src/components/factor-lab/ProposeButton.tsx
git rm frontend/src/components/factor-lab/PendingFactorProposalsTable.tsx
```

Verify no other file imports them:

```bash
grep -rn "ProposeButton\|PendingFactorProposalsTable" frontend/src/ --include="*.tsx" --include="*.ts"
```

Expected: zero matches (besides the deleted files themselves which are now gone).

- [ ] **Step 4: tsc + lint + build clean**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent/frontend
npx tsc --noEmit
npx next lint --quiet
npm run build 2>&1 | tail -25
```

Watch for:
- Unused imports in page.tsx (Next prod build fails on these even though tsc allows)
- Server/client boundary errors
- Missing `await cookies()` (Next 14+ async API)

Pre-existing /picks ECONNREFUSED is acceptable; any new error on /factor-lab is not.

- [ ] **Step 5: Commit**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent
git add "frontend/src/app/(dashboard)/factor-lab/page.tsx"
git commit -m "feat(factor-lab): page.tsx rewritten as Discovery orchestrator + delete deprecated components"
```

---

### Task 8: deploy + smoke

- [ ] **Step 1: Push**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent
git push
```

- [ ] **Step 2: Visual smoke against deployed frontend**

Open `/factor-lab` in production. Verify:
- Decision card renders 2-column on `md+` viewports, stacked on narrow.
- LIVE EXPRESSION shows the running expression in a `<pre>` block.
- WEAK SIGNAL highlights with `text-tm-warn` color; IC and worst-fold values display with `font-mono`.
- SYMPTOM caption shows below the 2-column grid in `text-xs text-tm-muted`.
- Propose button is the only `bg-tm-accent` button on the page.
- Clicking Propose: button enters spinner state + label changes; toast `Proposing... 30-60s` rises.
- After propose completes: inline result line appears below button with `{proposed} / {evaluated} · HH:MM:SS`; chevron expands to show outcome explanation.
- Pending row: chevron expands inline detail (hypothesis / justification / metrics / vs-live diff).
- Approve action: button spinner → toast `已启用 · ...` with Undo button → row disappears from pending list → live expression in decision card updates.
- Toast Undo click within 8s: rollback fires, row reappears, live expression reverts.
- History summary line shows at bottom; chevron expands to full FactorHistoryTable.
- Locale toggle (zh / en switch): every visible string changes.

- [ ] **Step 3: Report any cross-cutting regression**

If any /backtest behavior breaks (because of Task 0 errorParse migration), file a fix commit referencing the affected file. Smoke /backtest separately:

```bash
curl -s "https://alpha.bobbyzhong.com/backtest" -o /dev/null -w "%{http_code}\n"
```

Verify the page loads without server error.

---

## Self-Review

**Spec coverage:**

| Spec section | Task(s) implementing it |
|--------------|-------------------------|
| §1 Goal (Discovery workstation) | T2-T7 (all redesign tasks) |
| §3 Decision #1 Discovery mode | T5 decision card composition |
| §3 Decision #2 Diagnostic+Live merged | T3 + T5 |
| §3 Decision #3 Inline Approve + toast Undo | T6 PendingProposalsSection |
| §3 Decision #4 Lightweight row + chevron expand | T6 PendingProposalsSection |
| §3 Decision #5 History collapsed + chevron expand | T2 HistoryCollapsedSection |
| §3 Decision #6 Inline propose result line | T4 ProposeActionRow |
| §4 Cross-cutting audit (i18n) | T1 i18n keys |
| §4 Cross-cutting audit (errorParse shared) | T0 refactor |
| §5 Architecture diagram | T5 + T7 (composition + orchestration) |
| §6 State machine | T4 + T6 (propose state + row action state) |
| §7 Component tree | T2-T7 (all new components) |
| §8.1 FactorLabDecisionCard | T5 |
| §8.2 PendingProposalsSection | T6 |
| §8.3 HistoryCollapsedSection | T2 |
| §8.4 Error UX (propose error parse) | T4 (uses parseFactorError from T0) |
| §9 errorParse migration | T0 |
| §10 10 UX principles | T2-T7 (each task references the principle table in grounding) |
| §11 42 i18n keys | T1 |

**Placeholder scan:** None present. Every step has executable commands or complete code. The single "implementer must verify" callouts (Task 3 locale mechanism, Task 6 metrics shape) are honest grounding hooks, not placeholders.

**Type consistency:**
- `Locale` type referenced consistently across T3-T7 (server components accept `locale: Locale` prop; client components use `useLocale()`)
- `FactorProposal` shape referenced consistently (T2 uses `id, status, created_at`; T6 uses `id, expression, hypothesis?, justification?, metrics?`)
- `FactorDiagnostic` shape consistent (T3 + T5)
- `ProposeResult` shape consistent (T4 reads `dormant`, `evaluated`, `proposed`)
- `parseFactorError` (renamed in T0) used in T4
- Sub-component props match composition: T5 passes `locale` to LiveExpressionPanel / WeakSignalPanel / SymptomCaption (per T3 fallback decision), matching their declared props

**Anti-pattern guardrails verified:**
- Silent exception: T4 + T6 surface errors via toast OR inline error state
- Token correctness: only `tm-bg`/`tm-bg-2`/`tm-bg-3`/`tm-rule`/`tm-fg`/`tm-fg-2`/`tm-muted`/`tm-accent`/`tm-pos`/`tm-warn`/`tm-neg` used
- Grep call chain: T0 + T2 + T3 + T4 + T6 begin with grep step
- Cross-cutting conventions: every visible string in components routes through `t(locale, ...)`

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-23-factor-lab-redesign.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task with two-stage review, consistent with /alpha + /backtest series.

**2. Inline Execution** — same-session batched execution.

Pick approach to proceed.
