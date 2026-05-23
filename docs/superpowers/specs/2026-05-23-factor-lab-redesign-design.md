# /factor-lab Redesign Design Spec

> **Status:** Brainstorm complete 2026-05-23. Single-shot spec, no formal user review loop (user explicit preference).

## 1. Goal

Redesign `/factor-lab` from a 6-pane vertical stack into a Discovery workstation with one merged decision card anchoring the top, an inline-actionable pending proposals section, and a collapsed history summary at the bottom. Eliminate two production debts: zero `factorLab.*` i18n keys (entire page hardcoded English) and the `window.confirm()` modal on approve actions (violates Forgiveness principle).

## 2. Non-goals

- Backend changes to the propose endpoint (still accepts only `n`; no new params surfaced in UI).
- New diagnostic backend signals (current `weak_signal`, `IC`, `worst_fold_sharpe`, `symptom_summary` are sufficient).
- Sparkline / time-series visualizations on diagnostic data (would require new backend endpoint).
- Cross-device synchronization of pending state (already server-component fetched on each request).
- Multi-proposal batch approve.

## 3. Decisions locked (2026-05-23 brainstorm)

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | **Mode = Discovery workstation** | User flow is: diagnostic signal → decide whether to propose → review pending candidates → approve. The page is not primarily an approval-task surface; diagnostic context drives the action. |
| 2 | **Top anchor = Diagnostic + Live merged decision card** | The "why propose" logic chain (what's running, what's wrong with it, propose button) compresses into one viewport. Principle 1 Intent alignment locks at maximum. |
| 3 | **Approve = inline Approve/Reject buttons + toast Undo** | Eliminate `window.confirm()`. Undo via existing rollback endpoint. Toast duration extended to 8s (vs default 5s) because approve mutates live factor. |
| 4 | **Pending row = lightweight (expression + 1 metric + actions) + chevron expand** | Default row keeps table compact under multiple candidates; expand reveals hypothesis, justification, full metrics, vs-live diff. Principle 2 Cognitive load minimization. |
| 5 | **History = collapsed summary line + chevron expand to full table** | Audit reference value preserved without dominating viewport. "Past 30d: N proposed / A approved / R rejected / B rolled back" summary line is default; click to expand to existing FactorHistoryTable. |
| 6 | **Propose result feedback = inline result card in decision card + toast supplement** | Result line below propose button retains last propose outcome (with 4-state explanation: dormant / evaluated=0 / proposed=0 / proposed=N). Toast for transient running state and completion notification. |

## 4. Cross-cutting conventions audit

| Convention | Current state | Redesign must |
|------------|---------------|---------------|
| i18n keys (`factorLab.*`) | 0 keys, entire page hardcoded English | New `factorLab.*` namespace (~42 keys), zh + en parity. Single source of i18n truth. |
| Font convention | `font-tm-mono` used (page.tsx lines 42/56/61/82/93/107/112) | Preserve; expressions and numeric cells use `font-mono`, all labels and body text use `font-tm-mono`. |
| Layout wrappers | `TmScreen` + `TmPane` already used | Preserve. Decision card is a single TmPane wrapping a 2-column grid. |
| Locale-aware data | `useLocale` not yet imported (because 0 i18n keys) | Client components import `useLocale` from `@/components/layout/LocaleProvider`; server component reads locale from cookie/header and passes via `t(locale, ...)`. |
| Sidebar nav | Entry exists at `Sidebar.tsx:67` | No change; route remains `/factor-lab`. |
| Loading skeleton | `loading.tsx` exists (Phase UX-0) | Preserve. |
| Toast system | Phase UX-0 `useToast` available | Wire into all client action handlers (approve / reject / rollback / propose). |
| Token correctness | Already correct (fc64924 fix) | Preserve verified `tm-*` tokens; ban `tm-card` / `tm-line` / `tm-fg-1`. |
| errorParse helper | Lives in `components/backtest/errorParse.ts` | Move to `lib/factor-errors.ts` so both /backtest and /factor-lab share it. Update 4 /backtest imports. |

## 5. Architecture

```
[TmScreen, top to bottom]
+--------------------------------------------------+
|  FACTOR LAB DISCOVERY                            |  Page header (TmPane)
+--------------------------------------------------+
|  DECISION CARD                                   |  Section 1, anchor at top
|  +--------------------+--------------------+     |
|  | LIVE EXPRESSION    |  WEAK SIGNAL       |     |
|  | rank(ts_zscore...) |  momentum_5d       |     |
|  | deployed: 7d ago   |  IC = 0.012        |     |
|  |                    |  worst fold: -0.42 |     |
|  +--------------------+--------------------+     |
|  symptom: signal decayed across Q3-Q4 ...        |
|                                                  |
|  [ Propose factors (n=5) ]    ← Primary Action   |
|                                                  |
|  Last propose · 3 / 5 · 11:42:08 (chevron)       |  ← inline result line
+--------------------------------------------------+
|  PENDING PROPOSALS · 3 pending                   |  Section 2
|  > rank(ts_decay_linear(returns, 5)) DS=1.42 [✓][✗]
|  > ts_zscore(divide(volume, adv20), 60) DS=1.31 [✓][✗]
|  > group_neutralize(rank(close, sector)) DS=1.08 [✓][✗]
+--------------------------------------------------+
|  > HISTORY · 过去 30d: 12 提议 / 8 启用 / 4 拒绝   |  Section 3, collapsed
+--------------------------------------------------+
```

## 6. State machine

```
DecisionCardState
  ├─ diagnostic: FactorDiagnostic | null     (server-fetched)
  ├─ liveExpression: string                  (from diagnostic)
  ├─ proposeState:
  │    ├─ idle
  │    ├─ running                            (button spinner)
  │    ├─ ok       (carries ProposeResult: dormant / evaluated / proposed / queued)
  │    └─ error    (carries message string)
  └─ resultLineExpanded: boolean             (chevron state)

PendingSectionState
  ├─ proposals: FactorProposal[]             (server-fetched, filtered status=pending)
  └─ expandedRowIds: Set<string>             (per-row chevron toggle, client state)

HistorySectionState
  ├─ summary30d: { proposed, approved, rejected, rolledBack }  (derived from full history)
  └─ tableExpanded: boolean                  (chevron state)

ApproveFlow (per row, client state)
  ├─ idle | approving | rejecting
  └─ on success → router.refresh() → toast.success with Undo action

UndoFlow
  ├─ toast emits action.onClick → rollbackFactor(proposalId)
  └─ rollback succeeds → toast dismisses + router.refresh()
```

## 7. Component tree

```
<FactorLabPage>                                  // app/(dashboard)/factor-lab/page.tsx (rewrite ~150 lines)
  <FactorLabDecisionCard>                        // new, server component
    <LiveExpressionPanel />                        // new, server, left column
    <WeakSignalPanel />                            // new, server, right column
    <SymptomCaption />                             // new, server, cross-column caption
    <ProposeActionRow />                           // new, client, replaces ProposeButton.tsx
  </FactorLabDecisionCard>

  <PendingProposalsSection>                      // new, replaces PendingFactorProposalsTable.tsx
    <PendingRow>                                   // client, per-row state
      <RowHeadline />                                // expression + DS + Approve/Reject buttons
      <RowExpandedDetail />                          // chevron-expanded: hypothesis / justification / metrics / diff
    </PendingRow>
  </PendingProposalsSection>

  <HistoryCollapsedSection>                      // new, wraps FactorHistoryTable
    <HistorySummaryLine />                         // "30d: 12 / 8 / 4 / 0" + chevron
    <FactorHistoryTable proposals={history} />     // preserved as-is, mounted only when expanded
  </HistoryCollapsedSection>
</FactorLabPage>
```

## 8. Detailed section specs

### 8.1 FactorLabDecisionCard

A single TmPane title="DECISION" containing:

- 2-column CSS grid (`grid grid-cols-1 md:grid-cols-2 gap-4`).
- Left column: LiveExpressionPanel renders `diagnostic.current_expression` in a `<pre>` block with `font-mono`. Above the code, label `t(locale, "factorLab.decision.liveExpression")`. Below, deployed timestamp if available.
- Right column: WeakSignalPanel renders `diagnostic.weak_signal` highlighted with `text-tm-warn`. Below: IC value `(IC = 0.012)`, worst_fold_sharpe with color coding (negative = `text-tm-neg`), worst_fold_window date range in `text-tm-muted`.
- Below the 2-column grid, SymptomCaption renders `diagnostic.symptom_summary` in `text-xs text-tm-muted font-tm-mono`.
- Below the caption, ProposeActionRow:
  - Primary Action button: `bg-tm-accent text-tm-bg` "Propose factors (n=5)" with Loader2 + "Proposing... 30-60s" on running.
  - Below the button, when `proposeState.kind === "ok"`: result line `"Last propose · {proposed}/{evaluated} · HH:MM:SS"` + chevron. Click chevron expands to show `_explain(result)` text in `text-xs text-tm-fg-2`.
  - When `proposeState.kind === "error"`: red bar with parsed error summary + `<details>` collapsing raw message.

When `diagnostic === null`: entire card shows muted state with "Diagnostic unavailable" placeholder; Propose button still clickable (fallback path).

When `diagnostic.weak_signal === null`: WeakSignalPanel shows "No weak signal detected" muted; Propose button has small caption "live signal healthy — propose anyway?".

### 8.2 PendingProposalsSection

Wrapped in TmPane title=`t("factorLab.pending.title")` meta=`{n} pending`.

Row structure (default 42px height):
- Left: chevron icon button (toggle expand)
- Middle: expression text (truncated single line) + DS value
- Right: Approve button + Reject button (both outlined, border-tm-rule, small)

Row expanded (~280px):
- Expression block (`<pre>` wraps long expressions)
- HYPOTHESIS section: label + paragraph
- JUSTIFICATION section: label + paragraph
- METRICS section: IC / p-value / turnover / sharpe / max_dd / n_days as 2-row mono-spaced grid
- DIFF VS LIVE section: line-by-line diff with `-` red prefix for live, `+` green prefix for new

Empty state: `t("factorLab.pending.empty")` centered placeholder.

Approve handler:
1. `setState(approving)` → button shows spinner
2. `await approveFactorProposal(proposalId)`
3. On success: `toast.success(t("factorLab.toast.approved", { expression: shortExpr(proposal.expression) }), { action: { label: t("factorLab.toast.undo"), onClick: () => rollbackFactor(proposalId) }, duration: 8000 })`
4. `router.refresh()` (RSC re-fetch updates pending + history + decision card live expression)
5. On error: `toast.error(t("factorLab.toast.approveFailed"))`, leave row state idle, `router.refresh()` to sync truth

Reject handler: parallel to approve but calls `rejectFactorProposal` and toast says "Rejected" with Undo restoring to pending.

### 8.3 HistoryCollapsedSection

Default state: single line with `t("factorLab.history.summary30d", { n, a, r, b })` derived from `history` array filtered to last 30 days. Chevron right.

Expanded: chevron rotates down, full FactorHistoryTable mounts and renders. Preserve existing FactorHistoryTable component as-is (no rewrite of its 201 lines); HistoryCollapsedSection is purely a wrapper.

Summary derivation:
```typescript
const summary30d = {
  proposed: history.filter(p => withinDays(p.created_at, 30)).length,
  approved: history.filter(p => p.status === "approved" && withinDays(p.created_at, 30)).length,
  rejected: history.filter(p => p.status === "rejected" && withinDays(p.created_at, 30)).length,
  rolledBack: history.filter(p => p.status === "rolled_back" && withinDays(p.created_at, 30)).length,
};
```

### 8.4 Error UX

- Propose errors: VerdictBar-style parsed via shared `lib/factor-errors.ts::parseBacktestError` (renamed to `parseFactorError` after the move).
- Approve / Reject errors: toast.error only; row state returns to idle; `router.refresh()` re-syncs from server truth (in case of concurrent state change).
- Rollback errors: toast.error; the original approve/reject toast can stay visible until its 8s timer expires.

## 9. errorParse helper migration

Refactor step (Plan Task 1):
- Move `frontend/src/components/backtest/errorParse.ts` to `frontend/src/lib/factor-errors.ts`
- Update 4 imports in /backtest files (BacktestVerdictBar / EquityCurvePane / DrawdownPane / WalkforwardPane) + page.tsx
- Same exports `parseBacktestError` (rename to `parseFactorError` for namespace neutrality) + `ParsedError`
- /factor-lab imports from new location for propose error parsing

## 10. UX principles re-check

| # | Principle | How the redesign addresses it |
|---|-----------|-------------------------------|
| 1 | Intent alignment | Decision card co-locates diagnostic context with propose action; user does not navigate. |
| 2 | Cognitive load minimization | Default visible attention slots ≤ 10. Verbose content (hypothesis / justification / full history table / diff) collapsed by default. |
| 3 | Visibility of system status | Propose: spinner + toast + inline result line. Approve: button spinner + toast + RSC refresh. |
| 4 | Forgiveness | window.confirm eliminated. Approve/Reject have toast Undo (8s) calling rollback endpoint. Dormant state explained inline. |
| 5 | Affordance | Single accent button (Propose); secondary outlined (Approve/Reject); tertiary icons (chevron). |
| 6 | Design disappears | TmPane chrome unified across sections; user remembers task outcome, not UI structure. |
| 7 | No manual needed | Header caption explains workflow in one line. 4-outcome explanations inline. No overlay. |
| 8 | Respects user time | Propose surfaces 30-60s expectation. Approve sub-second + RSC refresh. |
| 9 | No dark patterns | 4 outcomes honestly explained. DS threshold tooltip visible. |
| 10 | One Primary Action | Propose is the only accent button on the page. |

## 11. i18n keys (42 total, zh + en parity)

Page chrome, decision card, propose action, 4 outcome explanations, pending proposals (column headers + actions), pending row expand (hypothesis / justification / metrics / diff labels), approve/reject/undo/error toast copy, history summary template. Exact list embedded in implementation plan; both blocks of `frontend/src/lib/i18n.ts` get the additions.

## 12. Out of scope (explicitly deferred)

- Batch approve multiple pending proposals.
- Diff between two pending proposals (only diff vs live in v1).
- Pinned baseline for comparison (no equivalent of /backtest baseline here).
- Exporting history to CSV.
- Backend-driven persistence of last propose outcome across sessions (currently client state only).
- Sparkline charts on diagnostic data.

---

**Next step**: `superpowers:writing-plans` to produce the implementation plan.
