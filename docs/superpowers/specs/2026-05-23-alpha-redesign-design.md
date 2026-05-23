# /alpha Redesign Design Spec

> **Status:** Brainstorm complete 2026-05-23. Awaiting user review before invoking writing-plans skill.

## 1. Goal

Redesign `/alpha` from a 1632-line, 11-pane, 12-state-flag research workstation into a focused decision-session page with one Primary Action ("TRANSLATE & BACKTEST"), a top verdict bar with traffic-light judgment, 3 evidence panes that fill progressively as APIs return, and smart analytics auto-expansion on failure. The redesign is driven by the Phase-3-era UX audit (2 Critical / 4 High violations) and the user's 10 UX principles (5 base + 5 quality differentiators).

## 2. Non-goals

- Building a multi-user collaborative experience (single user, single session).
- Replacing the existing backend translate / smoke / backtest endpoints (frontend orchestration only; backend stays as-is).
- Supporting all 3 use-modes (research workstation + capture session are deferred). Decision session is the only optimization target.
- Carrying over every existing pane verbatim (some analytics panes become collapsible; LLM.PROVENANCE is hidden unless an error involves the LLM).

## 3. Decisions locked (2026-05-23 brainstorm)

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | **Mode = decision session** | One dominant flow: write hypothesis -> translate -> see smoke IC -> backtest -> see Sharpe -> decide save / discard / iterate. Principle 10 (one Primary Action per screen) requires picking. |
| 2 | **Topology = TRANSLATE auto-chains to BACKTEST** | Single Primary Action button "TRANSLATE & BACKTEST". User accepts double cost (LLM + kernel) every click in exchange for one-click time-to-decision. |
| 3 | **Result layout = verdict bar + 3 evidence panes + 6 collapsed analytics** | Verdict bar is the highest-altitude visual anchor; 3 evidence panes (SPEC / SMOKE / BACKTEST) prove the verdict; analytics behind a single "Show all analysis" toggle (smart-expanded on failure). |
| 4 | **Loading UX = progressive reveal** | Each pane has independent skeleton state; SPEC fills after translate returns (~8s), SMOKE after probe (~9.5s), BACKTEST after backtest (~14.7s). Verdict bar updates progressively. User's time-to-first-info drops from ~15s to ~8s. |
| 5 | **Verdict expression = numbers + traffic-light + hover thresholds** | Show IC=0.034 ✓, Sharpe=1.23 ✓, maxDD=-12% ⚠ inline. Hover each metric for the threshold ("threshold >=0.02 considered useful"). Honors Principle 9 (no dark patterns) by exposing reasoning; honors Principle 1 (intent alignment) by encoding the user's question into the UI. |
| 6 | **Analytics = smart auto-expand on failure + "Show all" toggle** | LOOKAHEAD.GUARD leak detection, EXPRESSION.QUALITY score < 0.6, LLM.PROVENANCE error all auto-expand their pane and highlight it. Other panes stay collapsed unless user clicks Show all. Principle 1 (predict next step) lands here. |
| 7 | **History + Examples placement = state-gated inline + dropdown** | FACTOR.EXAMPLES becomes a chip row under the textarea visible only when textarea is empty. HYPOTHESIS.HISTORY becomes a dropdown in the input area header reachable from any state. No always-visible panes. |
| 8 | **Save-to-Zoo = one-click + toast with Undo** | [SAVE TO ZOO] writes the FactorSpec immediately and surfaces a toast.success("Saved to Zoo") with an Undo action that deletes the row. Honors Principle 4 (Forgiveness; Undo > confirmation). |
| 9 | **Errors = phased degradation** | Translate failure halts the chain (hard block, verdict bar red, "Edit hypothesis and retry"). Smoke or Backtest failure leaves earlier panes intact and shows error + Retry inside the failed pane; verdict bar shows partial metrics. Failed pane gets focus; user can save with partial info if they accept the tradeoff. |

## 4. Architecture

```
+----------------------------------------------------+
| <Topbar>  /alpha                                   |
+----------------------------------------------------+
| HYPOTHESIS.INPUT                  [History v]      |
|   <textarea>                                       |
|   Examples: [chip] [chip] [chip] (empty state)     |
|                            [TRANSLATE & BACKTEST]  |
+----------------------------------------------------+
| VERDICT BAR (top: idle / loading-stage / verdict)  |
|   IC=0.034 ✓  Sharpe=1.23 ✓  maxDD=-12% ⚠         |
|   [SAVE TO ZOO]                                    |
+----------------------------------------------------+
| 3 EVIDENCE PANES (side-by-side; lg screens)        |
|   | SPEC          | SMOKE         | BACKTEST     | |
|   | rank(...)     | IC sparkline  | equity curve | |
|   | operators[]   | IC=0.034      | Sharpe=1.23  | |
+----------------------------------------------------+
| [+ Show all analysis (5 panes)]  <- collapsed      |
|   (auto-expand on failure)                         |
+----------------------------------------------------+
```

The page is a single client component (most state is interactive). The 3 evidence panes each carry independent state machines: `idle | loading | ok | error`. The verdict bar is a derived view of the 3 pane states. The analytics-toggle reveals 5 panes that each render in <50ms (no async fetches; data is already in the result payload).

## 5. State machine

```
ChainState
├─ idle                      (no submission yet)
├─ translating               (translate API in flight)
├─ smoke_probing             (smoke API in flight; spec already populated)
├─ backtesting               (backtest API in flight; smoke already populated)
├─ done                      (all 3 completed)
└─ error                     (a stage failed; per-stage error state tracked separately)

Per-pane: PaneState = "waiting" | "loading" | "ok" | "error"
Pane states are mostly derived from ChainState but each pane can independently retry on soft error.

VerdictBar = derived from (chainState, paneStates, metrics)
  - chainState=idle      -> "Submit a hypothesis to start"
  - chainState=translating -> "Translating..." with progress indicator
  - chainState=smoke_probing -> "Probing smoke... | IC pending"
  - chainState=backtesting -> "Backtesting... | IC=0.034 ✓ | Sharpe pending"
  - chainState=done      -> full verdict with traffic-light marks
  - chainState=error AND translateError -> red bar, "Edit hypothesis and retry"
  - chainState=error AND smokeError or backtestError -> show available metrics + soft error
```

## 6. Component tree

```
<AlphaPage>
  <HypothesisInputCard>
    <TextareaWithCount />
    <HistoryDropdown />        # always present; populated from /api/hypothesis/history
    <ExamplesChips />           # visible only when textarea empty
    <UniverseSelector />        # SP500 / SP100 / etc (currently exists)
    <TranslateBacktestButton /> # Primary Action; disabled when textarea empty
  </HypothesisInputCard>

  <VerdictBar>
    <VerdictStateRenderer />    # picks renderer by ChainState
    <SaveToZooButton />          # visible when at least IC is known
  </VerdictBar>

  <EvidencePaneGrid>
    <SpecPane state={specState} data={specData} onRetry={...} />
    <SmokePane state={smokeState} data={smokeData} onRetry={...} />
    <BacktestPane state={backtestState} data={backtestData} onRetry={...} />
  </EvidencePaneGrid>

  <AnalyticsAccordion>
    # Default collapsed.
    # Auto-expand on: smokeData.lookahead_leak === true | smokeData.quality_score < 0.6 | provenance.error !== null
    <LookaheadGuardPane />
    <ExpressionQualityPane />
    <LlmProvenancePane />        # hidden entirely when provenance.error === null AND user has no BYOK debug intent
    <OperatorUsagePane />
    <HistoryInsightsPane />
  </AnalyticsAccordion>
</AlphaPage>
```

## 7. Detailed section specs

### 7.1 HypothesisInputCard
- **Textarea**: same content surface as today. Character count badge in pane header (right-aligned). Resize is `resize-y` (matches the existing /alpha; /backtest currently differs at `resize-none`; defer the /backtest fix to a later phase).
- **History dropdown**: button labelled "History v" in the top-right of the input card. Click opens a popover listing favorites + recent (preserving the current data model). Selecting an entry pre-fills the textarea + universe selector. Empty state inside popover: "No saved hypotheses yet."
- **Examples chips**: 6 chips below the textarea, visible only when `text.trim().length === 0`. Clicking a chip fills the textarea with its hypothesis text. The chip row vanishes the moment text is non-empty. Examples come from the existing `FACTOR_EXAMPLES` constant.
- **Universe selector**: a small dropdown adjacent to the Primary Action button. Default SP500. Preserves current behavior.
- **Primary Action button**: text "TRANSLATE & BACKTEST". Disabled when textarea empty or while ChainState is in any loading state. Visual dominance: `bg-tm-accent text-tm-accent-soft` (or whatever the project's strongest accent + soft-foreground combo is). All other interactive elements on the page use ghost / outlined / inline-link styles by comparison.

### 7.2 VerdictBar
A single horizontal bar spanning the page width, immediately below HypothesisInputCard. Tall enough to comfortably hold one line of metrics + the SaveToZoo button.

- **Idle state**: muted text "Submit a hypothesis above to start." No button visible.
- **Translating**: spinner + "Translating... ETA ~10s" (rough estimate; can refine later from historical timing).
- **Smoke probing**: "Translated. Probing smoke... | IC pending" - SPEC pane has already filled by this point.
- **Backtesting**: "IC=0.034 ✓ | Backtesting... | Sharpe pending" - SMOKE has filled; only Sharpe + DD are pending.
- **Done**: "IC=0.034 ✓ | Sharpe=1.23 ✓ | maxDD=-12% ⚠ | [SAVE TO ZOO]"
- **Error (translate)**: red bar, "✗ LLM JSON parse failed | [Re-translate]" - user-facing detail in a sub-line.
- **Error (smoke or backtest)**: partial metrics + soft warning, save button still active.

Thresholds (locked):
| Metric | ✓ | ⚠ | ✗ |
|--------|---|---|---|
| IC | ≥ 0.02 | 0 to 0.02 | < 0 |
| Sharpe | ≥ 1.0 | 0.5 to 1.0 | < 0.5 |
| maxDD | ≥ -15% | -25% to -15% | < -25% |

Hover any metric: tooltip with the threshold reasoning. Mobile: long-press or tap-twice.

### 7.3 Evidence panes (3)
Each is a TmPane variant with internal state:
- **SpecPane**: shows the parsed FactorSpec (expression + operators_used array). When ChainState=translating, shows a skeleton matching the eventual content height. On translate success, fills with the spec. On translate failure, shows the parse error + a "Re-translate" button.
- **SmokePane**: shows the smoke IC sparkline + IC value + lookahead_leak flag. Skeleton during smoke_probing. On success, shows the IC + sparkline. On failure, shows the error + "Retry smoke" button.
- **BacktestPane**: shows the backtest equity curve + Sharpe + drawdown bars. Skeleton during backtesting. On success, shows the chart + metrics. On failure, shows the error + "Retry backtest" button.

All three panes are visually equal in size (1/3 width each on lg screens, stacked on sm).

### 7.4 AnalyticsAccordion
A collapsed-by-default section below the evidence panes. Header: "[+] Show all analysis (5 panes)". Click to toggle expand/collapse all 5.

Auto-expand rules (any of these triggers expansion):
- `smoke.lookahead_leak === true` -> expand LookaheadGuardPane + highlight it with ⚠ badge.
- `smoke.expression_quality_score < 0.6` -> expand ExpressionQualityPane.
- `provenance.error !== null` -> expand LlmProvenancePane.
(Other panes never auto-expand; only via the Show-all toggle.)

When any pane is auto-expanded, the AnalyticsAccordion header becomes "[2 alerts] [+] Show 3 more analysis panes" so the user knows what they are looking at.

### 7.5 LlmProvenancePane
Currently always-shown even when content is meaningless ("platform default / ---"). New behavior:
- Render the pane content only when `provenance.error !== null` OR `provenance.debug_visible === true` (a user preference, defaults false).
- When hidden, the AnalyticsAccordion's "Show all" still surfaces it as the 5th pane (no information is permanently gone, just hidden by default).

### 7.6 Save-to-Zoo
- One click on [SAVE TO ZOO] in the verdict bar:
  1. POST to existing save endpoint with the current FactorSpec + smoke metrics + backtest metrics.
  2. On success, fire `toast.success("Saved to Zoo", { action: { label: "Undo", onClick: <reverse> } })`.
  3. On failure, fire `toast.error("Save failed: ...", { action: { label: "Retry", onClick: <retry> } })`.
- The Undo action calls a hypothetical DELETE endpoint (existing or to be confirmed; if the endpoint doesn't exist, the toast omits the Undo action and the implementation phase adds the endpoint).
- No confirmation modal.
- Button is enabled the moment IC is known (does not require backtest success).

### 7.7 Error UX

| Failure | Verdict bar | Affected pane | Other panes | Page reaction |
|---------|-------------|---------------|-------------|---------------|
| Translate fail | red bar "✗ LLM JSON parse failed" + [Re-translate] action | SPEC pane shows parse error + Re-translate button | SMOKE, BACKTEST remain in "waiting" skeleton | ChainState halts; user must edit hypothesis or click Re-translate |
| Smoke fail | yellow bar "Smoke probe failed | IC unavailable" | SMOKE pane shows error + Retry smoke button | SPEC remains OK; BACKTEST proceeds anyway (uses spec) | Chain proceeds to backtest if backend allows; otherwise halts at smoke fail |
| Backtest fail | yellow bar "IC=0.034 ✓ | Backtest failed" + Save still enabled | BACKTEST pane shows error + Retry backtest button | SPEC and SMOKE intact, Save button active | User can save with partial info |

When any pane is in error state, the AnalyticsAccordion stays collapsed (errors are surfaced in the evidence panes, not analytics). When auto-expansion fires for analytic-level warnings (lookahead leak), it stacks visually with any evidence-pane errors.

## 8. Migration strategy

The current `/alpha/page.tsx` is 1632 lines. The redesign cuts it down by:
- Removing 8 panes from the always-visible default layout (kept as conditional / inside accordion).
- Extracting HypothesisInputCard, VerdictBar, EvidencePaneGrid, AnalyticsAccordion into separate client components under `frontend/src/components/alpha/`.
- The page itself becomes a thin orchestrator (~150 lines): state machine + API calls + composition.

Estimated final state: page.tsx ~150 lines + ~5 new component files at ~80-200 lines each = ~900 lines total (down from 1632).

## 9. UX principles re-check

| # | Principle | How the redesign addresses it |
|---|-----------|-------------------------------|
| 1 | Intent alignment | One Primary Action; verdict bar answers "is this good?"; analytics auto-expand surfaces only what needs attention. |
| 2 | Cognitive load minimization | 3 panes default + 6 hidden; 1 Primary Action button; thresholds shown only on hover. |
| 3 | Visibility of system status | Progressive reveal shows partial results as soon as available; verdict bar continuously narrates state; toast confirms saves. |
| 4 | Forgiveness | Undo on Save; per-stage Retry on soft errors; no confirmation modals. |
| 5 | Affordance | Primary Action has strongest visual weight; ghost buttons for secondary; chip-style examples look like chips and are clickable. |
| 6 | Design disappears | After use, the user remembers "I made a factor" not "I navigated 11 panes". |
| 7 | No manual needed | Examples chips visible in empty state guide first-time users; History dropdown is discoverable from input header. |
| 8 | Respects user time | Progressive reveal gets first result on screen ~7s earlier than current; auto-chain saves one click per cycle. |
| 9 | No dark patterns | Thresholds visible on hover; verdict shows raw numbers alongside marks; no buried decisions. |
| 10 | One clear Primary Action | TRANSLATE & BACKTEST is unambiguous; SAVE TO ZOO appears only when relevant; History/Examples are passive affordances. |

## 10. Open implementation questions (resolve during plan-writing)

1. The current `/api/alpha/translate` may return smoke metrics in the same response as the FactorSpec, OR smoke may be a separate endpoint. The progressive-reveal model assumes 3 sequential calls. **Action**: during planning, grep the existing endpoints + decide whether to add a separate smoke endpoint or accept that SPEC and SMOKE fill simultaneously (still gives BACKTEST progressive reveal).
2. The Save-to-Zoo Undo affordance requires a delete endpoint. **Action**: confirm during planning whether `/api/zoo/{id}` DELETE exists; if not, add it as a planned task.
3. The HISTORY dropdown shape (popover vs full panel) - decide during planning based on what existing UI library / pattern the project favors.
4. ETA estimates for the loading-state ("Translating... ETA ~10s") - placeholder until we measure actual prod timings; can stay as rough estimates without real-time refinement.
5. Mobile breakpoint behavior for the 3-evidence-pane grid: stack vertically on `sm:`, side-by-side on `lg:`. Detailed responsive specifics during implementation.

## 11. Out of scope (explicitly deferred)

- Migrating /backtest, /factor-lab, or /evolution to similar patterns (separate per-page redesigns, per the user's page-by-page methodology).
- Onboarding flow / tour / tutorial (Principle 7 "no manual needed" is achieved via empty-state chips + dropdown discoverability; explicit onboarding not built).
- Real-time SSE streaming from backend (progressive reveal is achieved via 3 sequential frontend-orchestrated API calls; SSE is a deferred optimization).
- Persisting partial-result drafts (a translate that succeeded but backtest failed is not auto-saved; user must explicitly Save).
- Per-user threshold customization (locked at IC ≥ 0.02, Sharpe ≥ 1.0, maxDD ≥ -15% for v1; configurable thresholds are a future spec).

---

**Next step**: User reviews this spec. On approval, invoke `superpowers:writing-plans` to produce the implementation plan.
