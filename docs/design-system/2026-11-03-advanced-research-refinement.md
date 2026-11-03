# Advanced research workspace refinement

Date: 2026-11-03. Scope: Zoo, Evolution, BRAIN. Preceded by service-health classification release PR #67.

## Intent and boundary

Make saved factors reusable, pending changes reviewable, and mining outcomes legible. Preserve the cream/green workstation, shell, typography, TM primitives, data and existing actions. Refine composition and progressive disclosure; replace only repetitive or unbounded lists and misleading state representations. No new branding, investment logic, database schema or mining workflow.

## Findings and implementation

| Screen | Observed friction | Implemented change |
| --- | --- | --- |
| Zoo | Three local examples repeated in both top and bottom lists; catalog buried behind analytics; misleading server count | Catalog first, provenance, search/filter/sort, five-row default, full-expression dialog, confirmed deletion; small-sample charts withheld explicitly |
| Evolution | Header said zero pending while methodology queue had 117; large blank IC canvas; historical lists were either long or truncated | Combined loaded counts, unknown versus zero distinction, compact missing-data state, five-row paged review and ledger, secondary diagnostics disclosed |
| BRAIN | New-run settings blended with completed-run results; long expressions squeezed; successful LLM log looked like a warning | Separate composer/review, readable expression column, localized family and grade, collapsible diagnostics, ten-row result and candidate pages |
| BRAIN submission | A submission timestamp could represent an official rejection | Accepted, rejected and attempted/unconfirmed states use explicit receipt and persisted status; no retry offered where backend locks the attempted submission |

## Verification and limits

- Focused helper coverage: catalog filtering/sorting, evolution pagination and unknown counts, run-review and official receipt semantics. TypeScript and design-system audit are release checks.
- Browser checked actual components at the existing 1710×875 desktop viewport with the same captured data for both versions: three shipped local examples, 117 pending methodology proposals, 30 ledger records, actual BRAIN run #160 with eight rejected alphas and sixteen candidates. Negative outcomes were not changed for presentation.
- Checked Zoo detail and small-sample analytics, Evolution next-page transition, and one actual BRAIN alpha's PnL/yearly detail. No factor submission, mining, approval, production deletion or database write was performed.
- The temporary local review server blocks every non-GET API request. UI-only admin fixture is not an authorization test. Private BRAIN snapshots stay outside the repository; screenshots are the delivery evidence.
- A transient browser connection interruption was recovered without closing user tabs. The subsequent 1440px English desktop check found a Zoo action/date collision, which was corrected with explicit column budgets and compact action padding. All three pages then had no body or main horizontal overflow. Also verified candidate audit page 2 (items 11–16 of 16), Zoo empty search and deletion cancellation, plus BRAIN dark theme. The temporary viewport override is restored after checks.
- User visual acceptance remains separate from implementation and production deployment.

## Evidence artifacts

Before/after screenshots are stored in the local delivery directory:
`/Users/a22309/.codex/visualizations/2026/07/27/019fa455-20bf-7ca3-b1c9-94534e8bb207/`.

Pairs: `zoo-comparison-before-20261103.jpg` / `zoo-after-20261103.jpg`, `evolution-comparison-before-20261103.jpg` / `evolution-after-20261103.jpg`, `brain-comparison-before-20261103.jpg` / `brain-after-20261103.jpg`.

## Principle check

Status stays adjacent to the affected evidence. Composition follows reuse, review and simulation tasks. Recovery is pane-local where available. Defaults do not impersonate observations. Each workspace retains its primary action. Evidence is adjacent to decisions. All loaded records remain reachable. Missing and rejected data remain truthful. Shared keyboard-capable controls are retained. Density is desktop-oriented. Cross-page terminology and semantic colors come from the existing system.
