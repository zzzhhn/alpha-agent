# Frontend module consolidation plan

Status: proposed (2026-06-20). Survey of the current frontend information
architecture + concrete merge candidates, for the owner to greenlight before any
implementation. This is the UI-layer "merge over-split modules" the owner asked
for AFTER the 7-step backend roadmap (which is shipped). Implementation is NOT
started — this is the plan to review.

## Current IA (what exists today)

Nav is a single central config: `NAV_GROUPS` in
`frontend/src/components/layout/Sidebar.tsx` (L49-78), mounted once in
`app/(dashboard)/layout.tsx`. **13 sidebar entries across 3 groups**, every one
resolving to a real page (no broken links). The Topbar carries no nav.

| Group | Module | Route | One line |
|------|--------|-------|---------|
| RESEARCH | Alpha (因子 Alpha) | `/alpha` | Hypothesis-Lab: prose hypothesis → backtest chain. Headline differentiator. |
| RESEARCH | Backtest (回测) | `/backtest` | Factor backtest workbench (form → verdict → evidence). |
| RESEARCH | Factor Zoo (因子库) | `/factors` | Saved-factor hub; feeds backtest/report/screener via prefill. |
| RESEARCH | Signal (信号) | `/signal` | Single-factor live run: long/short baskets + IC + exposure. |
| RESEARCH | Report (报告) | `/report` | Full tear-sheet of a factor (KPIs + equity/dd/monthly + signal + exposure). |
| DECISIONS | Picks (今日推荐) | `/picks` | Daily ratings board (top-50) + ticker search. Default landing. |
| DECISIONS | Screener (选股) | `/screener` | Multi-factor basket builder + CSV export. |
| DECISIONS | Alerts (警报) | `/alerts` | Per-ticker alert feed. |
| DECISIONS | Evolution (演化监控) | `/evolution` | Self-evolution monitor: IC/calibration/adaptive-weights/changes/**proposals**. |
| DECISIONS | Factor Lab (因子实验室) | `/factor-lab` | Methodology decision card + **pending proposals** + history (49-line page). |
| REFERENCE | Data (数据) | `/data` | Universe + coverage + **operator catalog** + data sources. |
| REFERENCE | Methodology (方法论) | `/methodology` | Static reference: Data / **Operators** / Backtest tabs. |
| REFERENCE | Settings (设置) | `/settings` | BYOK creds + WeightsEditor + WatchlistEditor + ChangeLog. |

Plus `/stock/[ticker]` — a per-entity drill-down, correctly NOT in nav (deep-linked
from picks rows + alerts). No orphan/placeholder routes.

## Why consolidate (UI/UX principles at stake)

- **认知负担最小化**: 13 top-level slots is past the "scan without thinking"
  threshold; two pairs genuinely duplicate content, so the user has to learn
  which of two near-identical destinations to click.
- **意图对齐**: "演化监控" and "因子实验室" both being about the proposal/evolution
  lifecycle is unpredictable — a user can't guess they're separate.
- **好设计会消失**: collapsing duplicates means fewer destinations to remember.

## Merge candidates (ranked)

### C1 — Factor Lab → Evolution  (STRONGEST; recommend do)
- `/factor-lab` (`app/(dashboard)/factor-lab/page.tsx`, 49 lines) and `/evolution`
  both surface **methodology proposals**. `/evolution` already renders a
  `ProposalsTable`; `/factor-lab`'s own header comment says it "matches how
  /evolution handles proposals". Two nav slots (in different groups) for one
  lifecycle, one of them a thin 49-line page.
- **Proposal**: fold Factor Lab's `FactorLabDecisionCard` + `PendingProposalsSection`
  into `/evolution` as a top "Proposals / 决策" section above the read-only
  `ProposalsTable`. Remove the `/factor-lab` nav slot (keep the route as a
  redirect to `/evolution#proposals` for any deep links). DECISIONS group: 5 → 4.

### C2 — Signal → Report  (STRONG; recommend do, with a "quick look" caveat)
- `/report` already imports the SAME components `/signal` renders
  (`components/signal/TmTopBottomTable` + `TmExposureChart`, report L64-65) and
  fetches signal-today + exposure. `/signal`'s entire output is a subset of
  `/report`.
- **Proposal**: make `/signal` a "Live signal / 实时信号" tab (or first pane) inside
  `/report`; drop the standalone nav slot. RESEARCH group: 5 → 4. Caveat: `/report`
  is heavier (compare slot + print); if a lightweight quick-look is valued, keep a
  `/signal` route as a thin alias rather than deleting it.

### C4 — Data + Methodology → one "Reference" page  (OPTIONAL; do only if trimming REFERENCE)
- Both render an operator catalog (`/data` `OperandCatalog`; `/methodology`
  signature catalog) and data/schema info. `/data` is operational (live coverage %),
  `/methodology` is static.
- **Proposal**: one Reference page with tabs (Universe/Coverage | Operators |
  Backtest methodology), de-duplicating the operator catalog. REFERENCE: 3 → 2.
  Weaker win; only worth it to shrink the group.

### C3 — Watchlist edited in two places  (AUDIT NOTE, not a nav merge)
- Watchlist is editable inline (stars on picks/screener/stock/alerts) AND via a
  full `WatchlistEditor` in `/settings`. They appear to share `useWatchlist` state,
  so this is fine — flag only to prevent adding a THIRD edit surface. No nav change.

## Leave alone (deliberately)

`/alpha`, `/backtest`, `/factors`, `/picks`, `/screener`, `/alerts`,
`/stock/[ticker]`, `/settings` — each is a distinct surface with a real, separate
job (see survey). Do not merge.

## Risks any merge must respect

- **Prefill contracts**: `/factors` writes sessionStorage handoff keys
  (`alphacore.backtest.prefill.v1`, `…screener.prefill.v1`, `REPORT_PREFILL_KEY`)
  then `router.push`es to backtest/report/screener. A merge target must keep
  reading these.
- **Deep links**: `/stock/${ticker}`, `/alerts?ticker=`, `href="/settings"` (from
  stock/onboarding components), `href="/methodology"` (UniverseCard), signOut →
  `/picks`. A removed route needs a redirect.
- **i18n**: labels split across `lifecycle.*` and `nav.*` keys, two locale blocks
  each in `lib/i18n.ts`. A merge must prune the orphaned keys (C1 orphans
  `nav.factor-lab`; C2 orphans `lifecycle.signal`).
- **Active-state**: Sidebar active = exact `pathname === item.href`; a tab-based
  merge (`/evolution#proposals`) won't light the active marker without adjusting
  the match logic.
- **Fetch freshness**: `/factor-lab` uses `revalidate: 0` for proposals — preserve
  that when folding into `/evolution` (which mixes 60 / 0).

## Recommendation

Do **C1 + C2** (clear duplication, biggest cognitive-load win: 13 → 11 nav slots).
Treat **C4** as optional (only if shrinking REFERENCE is wanted), **C3** as a
do-not-regress audit note. Each merge ships behind the same discipline as the
backend work: keep old routes as redirects, prune i18n keys, verify deep links,
no behavior change to the surviving page beyond the added section/tab.
