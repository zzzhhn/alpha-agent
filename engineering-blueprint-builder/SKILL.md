---
name: engineering-blueprint-builder
description: |
  Generate production-grade engineering blueprint / PRD documents for software projects. Use this skill whenever the user asks to create a construction plan, system blueprint, technical PRD, module specification, or architecture document for any engineering project — especially when the output should be a professional .docx + .pdf deliverable with wireframe mockups, component-level specifications, acceptance criteria, and phased delivery plans. Also trigger when the user says "write a blueprint", "create a PRD", "plan the modules", "design the system spec", "construction document", or asks for a detailed engineering plan with visual artifacts. This skill encodes hard-won lessons about what makes a blueprint actually useful to an engineering team rather than a vague aspirational document.
---

# Engineering Blueprint Builder

A battle-tested pipeline for producing engineering blueprints that execution teams can actually build from. This skill uses **three layers of engineering** to ensure high-quality output:

1. **Prompt Engineering** — Precise instructions that tell the agent what to produce
2. **Context Engineering** — Reference files that ground the agent in domain knowledge and templates
3. **Harness Engineering** — Self-check gates that BLOCK progression if quality criteria aren't met

---

## HARD RULES — These Are Not Suggestions

The following rules exist because every single one was violated in production and caused rework. They are non-negotiable.

### Rule 1: ALWAYS Generate Visual Artifacts
Every module/section in the blueprint MUST have at least one visual diagram. No exceptions. If you find yourself writing a module without generating a visual, STOP and generate one before continuing.

Minimum visual requirements:
- **Executive Summary**: End-to-end pipeline architecture diagram (Mermaid + PNG)
- **Each module**: UI wireframe mockup showing the actual interface layout
- **Before/After comparison**: If optimizing an existing system, show current state vs proposed state side-by-side

### Rule 2: ALWAYS Produce Bilingual Output
Every blueprint MUST be delivered in both English AND Chinese (or whatever language pair the user needs). Not "if the user asks" — by default. Ask in Phase 1 which languages are needed; if the user doesn't specify, default to EN + ZH.

### Rule 3: ALWAYS Deliver .docx + .pdf
Never deliver only .docx. Word on macOS frequently fails to open docx-js output. Always convert to PDF via LibreOffice and deliver both.

### Rule 4: EVERY Table Must Have These Columns
When writing recommendation/specification tables, the following columns are MANDATORY:

| Column | Purpose | Example |
|--------|---------|---------|
| Item/Component | What is being specified | "Ticker Selector Bar" |
| Current State | What exists now (if applicable) | "Static HTML dropdown, no state" |
| Proposed State | What it should become | "React tabs with active highlight, URL sync" |
| Rationale (Why) | Why this change matters to the user | "Users need instant context switching; current reload takes 2s" |
| Implementation Detail | Engineering-level breakdown with steps | "1. Create TickerTab component... 2. Add React Router param..." |
| Acceptance Criteria | Falsifiable test condition | "Tab switch completes in <100ms; URL updates to /market?ticker=AAPL" |
| Expected Effect | Measurable improvement | "Reduces context-switch time from 2s to <100ms; eliminates page reload" |
| Effort | T-shirt size + hours estimate | "M (8-12h)" |

If you produce a table missing any of these columns, the table is INCOMPLETE. Add the missing columns before proceeding.

### Rule 5: PRD Depth — The "Emotional Layer" Test
Every module specification MUST answer these questions. If any answer is missing, the spec is incomplete:

1. **What anxiety does this module alleviate?** (e.g., "The user fears missing a market regime change that could wipe out positions")
2. **What is the user's mental model?** (e.g., "The user thinks of this as their 'cockpit dashboard' — all critical instruments at a glance")
3. **What does success feel like to the user?** (e.g., "The user glances at the screen and within 3 seconds knows if any action is needed")
4. **What is the current pain point?** (e.g., "Currently, the user must check 4 different terminal windows to get the same information")
5. **What is the product form?** (e.g., "A single-page card grid with real-time status dots, expandable on click")

---

## The Pipeline: 6 Phases with Gate Checks

```
Phase 1: Discovery & Constraint Gathering
    ↓ [GATE 1: Constraint Matrix complete?]
Phase 2: Codebase Exploration & Gap Analysis
    ↓ [GATE 2: Current State Assessment written?]
Phase 3: Deep Module Specification (PRD-Level)
    ↓ [GATE 3: Self-check — all 5 emotional questions answered per module?]
Phase 4: Visual Artifact Generation
    ↓ [GATE 4: Every module has ≥1 diagram? Before/after comparison exists?]
Phase 5: Document Assembly & Formatting
    ↓ [GATE 5: Manual TOC? Bilingual? Images embedded?]
Phase 6: Validation, Conversion & Delivery
    ↓ [GATE 6: .docx + .pdf both delivered? Both languages?]
```

### Gate Check Protocol

At each gate, STOP and verify. Do NOT proceed if any check fails.

```
GATE CHECK TEMPLATE:
□ [criterion 1] — pass/fail
□ [criterion 2] — pass/fail
□ [criterion 3] — pass/fail
If any fail → fix before proceeding
If all pass → continue to next phase
```

---

### Phase 1: Discovery & Constraint Gathering
**Read:** `references/phase1-discovery.md`

Use AskUserQuestion with structured multiple-choice options. Extract:

1. **Scope**: Full productization / Internal tool / Research prototype / Optimization of existing system
2. **Market/Domain**: Industry, data sources, user personas
3. **Budget**: Free-only data? Cloud API vs self-hosted? GPU budget?
4. **Security**: Dev mode OK? Rate limiting? Network hardening?
5. **Languages**: EN + ZH (default) / EN only / Other pair
6. **Audience**: Engineers / PMs / Investors / All
7. **Existing system?**: New build / Optimization of existing

**GATE 1 — Constraint Matrix:**
```
□ All 7 categories have explicit answers (not assumptions)
□ Language pair confirmed
□ Budget constraints documented
□ "Optimization vs new build" clarified
```

### Phase 2: Codebase Exploration & Gap Analysis
**Read:** `references/phase2-exploration.md`

If optimizing an existing system, this phase is CRITICAL. Explore thoroughly:
- Read every README, config file, and directory structure
- Identify module maturity (% complete)
- Map current tech stack
- Screenshot or describe current UI state (the "before")
- Note what the user said NOT to change

**GATE 2 — Current State Assessment:**
```
□ Current State Assessment section written with specific findings
□ Module maturity table populated (each module has a % and evidence)
□ "Before" state documented (for optimization projects)
□ Tech stack identified
```

### Phase 3: Deep Module Specification (PRD-Level)
**Read:** `references/phase3-specification.md`

This is where most blueprints fail. Each module MUST include ALL of the following sections — not "should include" but MUST:

1. **User Psychology & Pain Points** — Why this module exists emotionally. What anxiety it relieves. What the user's mental model is. What success feels like.

2. **Current vs Proposed State** — Table with: Current State, Problem, Proposed State, Expected Improvement. This is mandatory for optimization projects.

3. **Product Form & UX Specification** — What the user actually sees. Not "a dashboard" but "a 3-column grid of status cards, each 280px wide, with a green/yellow/red status dot in the top-right corner. Clicking a card expands it inline to show a 30-day sparkline."

4. **Component Inventory** — Table with ALL mandatory columns (Item, Current State, Proposed State, Rationale, Implementation Detail, Acceptance Criteria, Expected Effect, Effort)

5. **User Interaction Flows** — Step-by-step: "User opens page → sees X → hovers Y → tooltip shows Z → clicks W → panel expands with data from /api/foo"

6. **Data Contracts** — Exact JSON structures from each API endpoint

7. **Acceptance Criteria** — Numbered, falsifiable, testable. Template: "[metric] [operator] [threshold], verified by [method]"

8. **Edge Cases & Error States** — Stale data, API failure, NaN, narrow viewport, empty state, rate limited, auth expired

**GATE 3 — PRD Quality Self-Check:**
```
For EACH module:
□ All 5 emotional questions answered (anxiety, mental model, success feeling, pain point, product form)
□ Current vs Proposed table exists (for optimization projects)
□ Component Inventory table has all 8 mandatory columns
□ At least 3 User Interaction Flows documented
□ At least 1 Data Contract (JSON) provided
□ Every AC passes the falsifiability test ("Can an engineer write a test for this?")
□ At least 5 edge cases identified
□ ZERO instances of vague language ("correctly", "properly", "should work", "displays normally")
```

**If any module fails any check, fix it before Phase 4.**

### Phase 4: Visual Artifact Generation
**Read:** `references/phase4-visuals.md`

TWO types of visuals are mandatory:

**Type A: Architecture / Flow Diagrams (Mermaid)**
Use Mermaid syntax for architecture diagrams, data flows, and state machines. Mermaid is preferred because:
- It renders consistently in Markdown, HTML, and PDF
- It's version-controllable (text, not binary)
- It can be edited by engineers without design tools

Generate `.mermaid` files and render to PNG using `mmdc` (mermaid-cli) or embed as code blocks.

Minimum Mermaid diagrams:
- Pipeline architecture (end-to-end data flow)
- Module dependency graph
- State machine for key entities (e.g., order lifecycle)

**Type B: UI Wireframes (Pillow PNG)**
Use Python + Pillow for detailed UI wireframes showing:
- Actual layout with sidebar, header, content areas
- Realistic sample data (not "Lorem ipsum" — use domain-specific data)
- Color-coded status indicators
- Interactive states (hover, selected, expanded)

Minimum wireframes:
- 1 per module (showing the module's primary view)
- 1 architecture overview for Executive Summary

**Type C: Before/After Comparison (for optimization projects)**
If optimizing an existing system, create a side-by-side or sequential comparison showing:
- BEFORE: Current UI / architecture (screenshot description or wireframe of current state)
- AFTER: Proposed UI / architecture (wireframe of proposed state)
- DELTA: What specifically changed and why

**GATE 4 — Visual Artifact Check:**
```
□ ≥1 Mermaid architecture diagram generated
□ ≥1 wireframe PNG per module generated
□ Executive Summary has pipeline overview diagram
□ Before/after comparison exists (optimization projects)
□ All diagrams use realistic sample data, not placeholders
□ All PNGs saved to images/ directory with sequential naming (00_, 01_, ...)
```

### Phase 5: Document Assembly & Formatting
**Read:** `references/phase5-assembly.md`

Critical rules:
1. **Manual TOC** — NEVER use docx-js TableOfContents (it generates empty field codes). Build manual TOC with InternalHyperlink + dot-leader tabs.
2. **Bilingual** — Generate EN and ZH (or configured pair) as parallel scripts. Different bookmark ranges (200-series EN, 500-series ZH).
3. **Images embedded** via ImageRun with all three altText fields.
4. **Page size**: US Letter (12240×15840 DXA) explicit.

**GATE 5 — Document Assembly Check:**
```
□ Manual TOC has entries for ALL sections (not empty)
□ Both language versions generated
□ All wireframe PNGs embedded in document
□ All Mermaid diagrams embedded (rendered to PNG first)
□ Cover page has version, date, classification
□ Header/footer with page numbers
```

### Phase 6: Validation, Conversion & Delivery
**Read:** `references/phase6-delivery.md`

1. Validate: ZIP integrity, XML well-formedness, structural counts
2. Convert BOTH language versions to PDF via LibreOffice
3. Deliver ALL files (2× .docx + 2× .pdf = 4 files minimum) with computer:// links

**GATE 6 — Delivery Check:**
```
□ EN .docx generated and validated
□ EN .pdf generated
□ ZH .docx generated and validated
□ ZH .pdf generated
□ All 4 files saved to workspace folder
□ All 4 files have computer:// links provided to user
□ File sizes are reasonable (>50KB for docx with images, >100KB for PDF)
```

---

## Anti-Pattern Catalog

These are the specific failures this skill exists to prevent. If you catch yourself doing any of these, STOP and correct:

| Anti-Pattern | What It Looks Like | What To Do Instead |
|---|---|---|
| **The Aspirational Fog** | "The system should be fast and reliable" | "Response time <500ms p95 under 100 req/s load, verified by k6 load test" |
| **The Architecture Astronaut** | Boxes and arrows with no UI detail | Draw the actual screen. Every button, every card, every tooltip. |
| **The Table Skeleton** | 3-column table with Item/Detail/Effort | 8-column table: Item/Current/Proposed/Rationale/Implementation/AC/Effect/Effort |
| **The Missing Visual** | 10 pages of text, zero diagrams | Generate Mermaid architecture diagram + Pillow wireframe per module |
| **The Monolingual Default** | English-only output | Always EN + ZH (or configured pair) |
| **The Empty TOC** | TableOfContents field code that Word shows as blank | Manual TOC with InternalHyperlink + PositionalTab |
| **The .docx-Only Delivery** | .docx that can't open in Word on macOS | Always deliver .docx + .pdf pair |
| **The Surface PRD** | "Optimize the dashboard" with no user psychology | Answer: What anxiety? What mental model? What does success feel like? |
| **The Missing Delta** | "Here's the new design" with no comparison to current | Before/After comparison table + visual diff |

---

## Failure Catalog

Read `references/failure-catalog.md` for 15 documented failures from the Alpha Core project with root causes, impact, fixes, and preventive rules.

---

## Quick Start Checklist

When this skill triggers, execute in order:

```
1. □ Read references/phase1-discovery.md
2. □ AskUserQuestion to gather constraints (MANDATORY — do NOT skip)
3. □ GATE 1: Constraint Matrix complete? → if no, ask more questions
4. □ Read references/phase2-exploration.md
5. □ Explore codebase (if exists); document current state
6. □ GATE 2: Current State Assessment written? → if no, explore more
7. □ Read references/phase3-specification.md
8. □ Write deep module specs with ALL mandatory sections
9. □ GATE 3: Self-check emotional questions + table columns + AC falsifiability
10. □ Read references/phase4-visuals.md
11. □ Generate Mermaid architecture diagrams
12. □ Generate Pillow wireframe PNGs for every module
13. □ Generate before/after comparison (if optimization project)
14. □ GATE 4: Every module has ≥1 diagram? Before/after exists?
15. □ Read references/phase5-assembly.md
16. □ Build EN .docx with manual TOC, embedded images
17. □ Build ZH .docx with manual TOC, embedded images
18. □ GATE 5: Both docs have TOC, images, bilingual content?
19. □ Read references/phase6-delivery.md
20. □ Convert both to PDF
21. □ GATE 6: 4 files delivered with computer:// links?
```

Total expected time: 20-40 minutes for a multi-module system with wireframes and bilingual output.
