# Phase 3: Specification — PRD-Level Module Specification Protocol

**Purpose:** Create engineer-ready specifications that are also product-ready. Every module has clear responsibilities, user psychology grounding, testable acceptance criteria, and defined data contracts.

**ENFORCEMENT:** This phase has the highest failure rate in production. The two most common failures are: (1) tables with only 3 columns instead of 8, and (2) specs that describe what the system does but not why the user cares. Both are blocked by Gate 3.

---

## MANDATORY: The Emotional Layer (5 Questions Per Module)

Before writing ANY technical specification for a module, answer these 5 questions. If any answer is missing, the module spec is INCOMPLETE and must not proceed to Phase 4.

### Question Template

```markdown
### User Psychology & Pain Points

**1. What anxiety does this module alleviate?**
> [What the user fears will go wrong without this module]

**2. What is the user's mental model?**
> [How the user thinks about this module — what metaphor or analogy fits]

**3. What does success feel like to the user?**
> [The emotional state when this module works perfectly]

**4. What is the current pain point?**
> [Specific, measurable frustration the user has today]

**5. What is the product form?**
> [Concrete description of what the user sees — not "a dashboard" but specifics]
```

### BAD vs GOOD Examples

**BAD (The Surface PRD):**
```
1. Anxiety: Users want reliability
2. Mental model: It's a dashboard
3. Success: It works well
4. Pain point: Current system is slow
5. Product form: A monitoring page
```
(Every answer is vague. An engineer cannot build from this.)

**GOOD (The Deep PRD):**
```
1. Anxiety: "The user fears missing a market regime change that could wipe out
   30% of portfolio value in 48 hours. The last time this happened (March 2020),
   the user didn't detect the shift for 3 days."

2. Mental model: "The user thinks of this as their 'cockpit dashboard' — all
   critical instruments visible at a glance, with red/yellow/green indicators
   that require zero interpretation. Like a pilot scanning instruments on
   final approach."

3. Success: "The user opens the page and within 3 seconds knows: (a) current
   regime state, (b) whether any position needs immediate action, (c) confidence
   level of the model's current prediction. No clicking required."

4. Pain point: "Currently, the user must check 4 different terminal windows
   (TradingView, Bloomberg Terminal, a Python REPL, and a Slack channel) to
   assemble the same information this module provides in one view. This takes
   ~12 minutes per check, done 5x/day = 1 hour/day wasted."

5. Product form: "A single-page card grid with 4 status cards (each 280px wide,
   dark theme). Each card has: (a) a green/yellow/red status dot top-right,
   (b) a 30-day sparkline chart, (c) current value in large text, (d) 24h delta
   in smaller text below. Cards expand on click to show a detail panel with
   the last 90 days of history."
```

---

## Module Specification Template

Create one of these per module. ALL sections are MANDATORY — not "should include" but MUST include.

```markdown
# [ModuleName] Module Specification

## 1. User Psychology & Pain Points
[Answer all 5 emotional questions — see template above]

## 2. Current vs Proposed State (MANDATORY for optimization projects)
[Table comparing before and after — see format below]

## 3. Product Form & UX Specification
[What the user actually sees — pixel-level detail]

## 4. Component Inventory
[8-column table — see MANDATORY format below]

## 5. User Interaction Flows
[Step-by-step flows — minimum 3 per module]

## 6. Data Contracts
[JSON Schema for each key data structure]

## 7. Acceptance Criteria
[Numbered, falsifiable, testable]

## 8. Edge Cases & Error States
[Minimum 5 per module]
```

---

## Section 1: User Psychology & Pain Points

See "MANDATORY: The Emotional Layer" above. All 5 questions must be answered with specific, concrete details. No vague answers.

**Self-check:** Read each answer aloud. If it could apply to ANY module in ANY project, it's too vague. Rewrite with specifics.

---

## Section 2: Current vs Proposed State

**MANDATORY for optimization projects. Skip ONLY for greenfield new builds.**

| Aspect | Current State | Problem | Proposed State | Expected Improvement |
|--------|--------------|---------|---------------|---------------------|
| Data refresh | Manual CSV import, 1x/day | 23-hour data lag; user makes decisions on stale data | WebSocket real-time feed | Data lag reduced from 23h to <500ms |
| Regime detection | User eyeballs charts manually | Subjective; misses subtle shifts; 3-day detection delay | HMM 4-state model with auto-alerts | Detection time from 72h to <4h |
| Risk display | Separate terminal window | Context-switching wastes 12 min/check | Inline risk panel with VaR gauge | Zero context-switching; 3-second assessment |

**Self-check:** Does every row have a measurable "Expected Improvement"? If not, add one.

---

## Section 3: Product Form & UX Specification

This section describes what the user actually sees. Not "a dashboard" but the exact layout.

**Template:**
```markdown
### Layout
- Page structure: [e.g., "3-column grid of status cards, each 280px wide"]
- Navigation: [e.g., "Left sidebar with 7 module icons, active module highlighted blue"]
- Header: [e.g., "Module name + last-updated timestamp + refresh button"]

### Visual Elements
- Primary display: [e.g., "4 KPI cards in a row: Regime State, Portfolio VaR, Active Signals, P&L Today"]
- Each card contains: [e.g., "Title (12px, dim), Value (24px, bold), Delta (14px, green/red), 30-day sparkline (60px tall)"]
- Status indicators: [e.g., "8px dots: green = normal, yellow = warning, red = critical"]
- Color coding: [e.g., "Dark theme: BG #0F1117, Card #1A1D27, Accent #2E75B6"]

### Interactive States
- Default: [what user sees on page load]
- Hover: [what changes on hover — tooltips, highlights]
- Click/Expand: [what happens on click — panels, modals, detail views]
- Loading: [skeleton screens, spinners, progress bars]
- Error: [what user sees when data fails to load]
- Empty: [what user sees when no data exists yet]
```

**Self-check:** Can a frontend engineer build this UI from this description alone, without asking questions? If not, add more detail.

---

## Section 4: Component Inventory — MANDATORY 8-COLUMN TABLE

**THIS IS THE MOST COMMONLY FAILED REQUIREMENT.** The table MUST have exactly these 8 columns. If you produce a table with fewer columns, it is INCOMPLETE. Stop and add the missing columns.

| Column | What Goes Here | Example |
|--------|---------------|---------|
| **Item/Component** | What is being specified | "Ticker Selector Bar" |
| **Current State** | What exists now (if applicable) | "Static HTML dropdown, no state" |
| **Proposed State** | What it should become | "React tabs with active highlight, URL sync" |
| **Rationale (Why)** | Why this change matters to the user | "Users need instant context switching; current reload takes 2s" |
| **Implementation Detail** | Engineering-level breakdown with numbered steps | "1. Create TickerTab component with props: tickers[], active, onChange 2. Add React Router search param sync 3. Debounce tab switch by 100ms" |
| **Acceptance Criteria** | Falsifiable test condition | "Tab switch completes in <100ms; URL updates to /market?ticker=AAPL; active tab has blue underline" |
| **Expected Effect** | Measurable improvement | "Reduces context-switch time from 2s to <100ms; eliminates full page reload" |
| **Effort** | T-shirt size + hours estimate | "M (8-12h)" |

### Full Example Row

| Item | Current State | Proposed State | Rationale | Implementation Detail | Acceptance Criteria | Expected Effect | Effort |
|------|--------------|----------------|-----------|----------------------|--------------------|-----------------|----|
| Regime Status Card | No equivalent; user checks Bloomberg terminal | Real-time card showing HMM state + confidence + transition probability | User loses 12 min/day checking external tools; misses regime shifts by avg 3 days | 1. Create RegimeCard React component 2. Subscribe to WebSocket /ws/regime 3. Display: state name (large), confidence % (gauge), transition matrix (mini heatmap) 4. Add pulse animation on state change 5. Cache last 24h of states for sparkline | Card updates within 500ms of model output; confidence gauge renders 0-100% range; state change triggers 2s pulse animation; card renders correctly at 280px and 360px widths | Eliminates 1h/day of manual checking; reduces regime detection lag from 72h to <4h; user never needs to leave the platform | M (10-14h) |

### Anti-Pattern: The 3-Column Table

**NEVER produce this:**

| Recommendation | Implementation Detail | Effort |
|---|---|---|
| Add regime detection | Implement HMM model | M |

This table is missing 5 columns: Current State, Proposed State, Rationale, Acceptance Criteria, Expected Effect. It tells the engineer WHAT to build but not WHY, not HOW TO TEST IT, and not WHAT IMPROVEMENT TO EXPECT.

---

## Section 5: User Interaction Flows

**Minimum 3 flows per module.** Format: step-by-step from user action to final system state.

### Flow Template

```markdown
### Flow: [Name] (e.g., "User Detects Regime Change")

1. **Trigger:** [What initiates the flow]
   → User opens Market Feed page at 9:30 AM ET

2. **System Response:** [What the system shows]
   → Page loads in <1s; 4 status cards render with latest data
   → Regime card shows "Bull (High Vol)" with 87% confidence

3. **User Action:** [What the user does next]
   → User notices regime card has yellow border (regime changed in last 4h)
   → User clicks regime card to expand detail panel

4. **System Response:** [What happens on interaction]
   → Detail panel slides open (200ms animation)
   → Shows: transition history (last 30 days), current state probabilities,
     model ensemble agreement (3/3 models agree)

5. **User Decision:** [What the user decides]
   → User sees high confidence in new regime
   → Clicks "View Affected Positions" button in detail panel

6. **System Response:** [Final state]
   → Navigates to Portfolio Risk view, pre-filtered to positions with
     >10% sensitivity to current regime
   → Risk table highlights 3 positions needing attention

7. **Final State:** [What's different after the flow]
   → User identified regime change + affected positions in <60 seconds
   → Previously took ~15 minutes across 4 separate tools
```

### Flow Categories to Cover

1. **Happy path** — Everything works perfectly
2. **Error recovery** — API fails, data is stale, model returns NaN
3. **First-time use** — Empty state, onboarding, no historical data

---

## Section 6: Data Contracts

Provide exact JSON structures for each API endpoint this module uses.

```json
// GET /api/regime/current
{
  "state": "bull_high_vol",
  "state_label": "Bull (High Volatility)",
  "confidence": 0.87,
  "transition_probabilities": {
    "bull_high_vol": 0.72,
    "bull_low_vol": 0.15,
    "bear_high_vol": 0.10,
    "bear_low_vol": 0.03
  },
  "model_agreement": {
    "hmm": "bull_high_vol",
    "xgboost": "bull_high_vol",
    "lstm": "bull_high_vol",
    "agree": true,
    "agreement_ratio": 1.0
  },
  "last_transition": {
    "from": "bull_low_vol",
    "to": "bull_high_vol",
    "at": "2026-04-13T06:15:00Z",
    "hours_ago": 3.25
  },
  "updated_at": "2026-04-13T09:30:05Z"
}
```

**Self-check:** Can a frontend developer build the UI component using ONLY this JSON contract? If they'd need to ask "what field has X data?" the contract is incomplete.

---

## Section 7: Acceptance Criteria

### The Falsifiability Test

Every acceptance criterion MUST pass this test: **"Can an engineer write an automated test that either passes or fails based on this criterion?"**

If the answer is no, rewrite it.

### Format Template

```
AC-[module]-[number]: [metric] [operator] [threshold], verified by [method]
```

### BAD vs GOOD Examples

| # | BAD (Vague) | GOOD (Falsifiable) |
|---|---|---|
| 1 | "Works correctly" | "POST /api/regime returns 200 with valid JSON matching schema within 200ms (p95), verified by k6 load test at 50 req/s" |
| 2 | "Is performant" | "Page initial load <1.5s on 4G connection (Lighthouse performance score ≥90), verified by CI Lighthouse run" |
| 3 | "Handles errors gracefully" | "When WebSocket disconnects, UI shows 'Reconnecting...' banner within 1s; auto-reconnects within 5s; no data loss on reconnect, verified by Cypress test that kills WS mid-stream" |
| 4 | "Displays normally" | "Regime card renders correctly at 280px, 360px, and 480px widths; text never truncates; sparkline scales proportionally, verified by Playwright visual regression test" |
| 5 | "Data is up to date" | "Regime state updates within 500ms of model inference completion, verified by comparing model output timestamp vs UI render timestamp in integration test" |
| 6 | "User-friendly" | "New user completes 'identify current regime' task in <30s without documentation, verified by usability test with 5 participants" |
| 7 | "Secure" | "API returns 401 for requests without valid JWT; returns 403 for valid JWT without 'regime:read' scope; verified by integration test suite" |
| 8 | "Scalable" | "System handles 500 concurrent WebSocket connections with <100ms broadcast latency, verified by k6 WebSocket load test" |

### Zero Tolerance for Vague Language

These words/phrases are BANNED in acceptance criteria:
- "correctly" → specify what "correct" means
- "properly" → specify the exact behavior
- "should work" → specify the observable outcome
- "displays normally" → specify viewport, browser, and visual expectation
- "handles gracefully" → specify the error message, timing, and recovery
- "is fast" → specify the latency threshold and measurement method
- "is reliable" → specify the uptime %, failure mode, and recovery time

---

## Section 8: Edge Cases & Error States

**Minimum 5 edge cases per module.** Use this category checklist:

| Category | What Could Go Wrong | How to Handle | How to Test |
|----------|-------------------|---------------|-------------|
| **Stale Data** | WebSocket disconnects; data is 5 minutes old | Show "Data may be stale (last update: 5m ago)" warning; dim status dots to gray | Mock WS disconnect; verify warning appears after 30s timeout |
| **API Failure** | /api/regime returns 500 or times out | Show last-known-good data with "⚠ Using cached data" label; retry every 10s with exponential backoff | Mock 500 response; verify cached data shown + retry behavior |
| **NaN / Invalid** | Model returns NaN confidence or negative probability | Display "—" for value; show "Model Error" badge on card; log to error tracking | Send NaN in mock response; verify UI doesn't crash and shows fallback |
| **Narrow Viewport** | User on 1024px laptop screen | Cards reflow to 2-column grid; sparklines shrink proportionally; no horizontal scroll | Resize browser to 1024px; verify layout with Playwright screenshot |
| **Empty State** | No regime data yet (fresh deployment) | Show skeleton cards with "Awaiting first model run..." message | Load page with empty database; verify skeleton UI renders |
| **Rate Limited** | API returns 429 Too Many Requests | Queue requests; show "Rate limited — retrying in {n}s" toast; respect Retry-After header | Mock 429 with Retry-After: 5; verify client waits 5s before retry |
| **Auth Expired** | JWT token expired mid-session | Show "Session expired" modal; redirect to login on confirm; preserve current page URL for redirect-back | Let token expire during active session; verify modal appears and redirect works |
| **Clock Skew** | Client time differs from server time by >30s | Use server timestamp for all time-relative displays (e.g., "3 min ago"); never rely on client Date.now() for business logic | Set client clock 5 minutes ahead; verify "last updated" still shows correct relative time |
| **Concurrent Updates** | Two users modify same resource simultaneously | Last-write-wins with version field; show "Updated by another user" if version conflict | Simulate concurrent PUT with same version; verify 409 returned for second request |
| **Partial Load** | 3 of 4 API calls succeed, 1 fails | Render available cards; show error state only on failed card; don't block entire page | Mock one endpoint as 500, others as 200; verify partial render |

---

## GATE 3 — PRD Quality Self-Check

**STOP HERE. Do not proceed to Phase 4 until every check passes.**

```
For EACH module, verify:

□ All 5 emotional questions answered with specific, concrete details
  (not vague — could NOT apply to any other module)
□ Current vs Proposed table exists (for optimization projects)
  with measurable "Expected Improvement" in every row
□ Product Form describes exact layout (widths, colors, positions)
□ Component Inventory table has ALL 8 mandatory columns:
  Item | Current State | Proposed State | Rationale | Implementation Detail |
  Acceptance Criteria | Expected Effect | Effort
□ At least 3 User Interaction Flows documented
  (happy path + error recovery + first-time use)
□ At least 1 Data Contract (JSON) per API endpoint
□ Every Acceptance Criterion passes the falsifiability test
  ("Can an engineer write an automated test for this?")
□ Zero instances of banned vague language
  ("correctly", "properly", "should work", "displays normally",
   "handles gracefully", "is fast", "is reliable")
□ At least 5 edge cases identified with handling strategy and test method
□ Edge cases cover at least 4 of these categories:
  stale data, API failure, NaN, narrow viewport, empty state,
  rate limited, auth expired, concurrent updates

RESULT: □ ALL PASS → proceed to Phase 4
        □ ANY FAIL → fix before proceeding
```

**If any module fails any check, fix it before Phase 4.**
