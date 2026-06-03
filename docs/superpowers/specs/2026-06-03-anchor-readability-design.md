# Anchor-Page Readability Redesign (Picks + Stock Detail)

Date: 2026-06-03
Scope: L1 (type scale + mono policy + contrast) and L2 (hierarchy + density) on
`/picks` and `/stock/[ticker]`. Terminal (Bloomberg) aesthetic fully preserved;
only readability, density, and hierarchy change. No backend changes.

## Problem (grounded, measured)

- 40+ sub-12px text instances with no coherent scale (8 / 9 / 9.5 / 10 / 10.5 /
  11 px), source: grep over `components/picks` + `components/stock`.
- dark `--tm-muted` = #6c7280 (~4.2:1, below AA 4.5:1) used on 8-11px labels.
- 47 monospace usages across the two pages; mono is on labels/sources/badges,
  not just numbers.
- Stock detail main column = 10 equal-weight blocks stacked with `space-y-8`,
  only 1 has an `<h2>`. No primary/secondary tiering.

## L1 design system

### Type scale (6 steps, replaces all arbitrary values)

| name  | px | class            | use                                   |
|-------|----|------------------|---------------------------------------|
| micro | 11 | `text-[11px]`    | units, badges, sub-labels, stale tags |
| data  | 12 | `text-xs`        | dense tabular numbers / table cells   |
| body  | 13 | `text-[13px]`    | secondary prose, news meta            |
| label | 14 | `text-sm`        | row text, section sub-headers         |
| title | 17 | `text-[17px]`    | block headings (`<h2>`)               |
| hero  | 22 | `text-2xl`       | ticker / page hero                    |

Floor rule: nothing below 11px. Map 8 / 9 / 9.5 / 10 / 10.5 px -> 11px (labels)
or 12px (numeric table cells).

### Mono policy

`font-tm-mono` + `tabular-nums` ONLY on numeric content (price, z, %, composite,
IC, count, data-dates). Labels, ticker links, source tags, headlines, prose ->
default sans (`font-tm-sans` / inherit). This alone removes the "wall of code".

### Contrast

- dark `--tm-muted`: #6c7280 -> #868d99 (~5.6:1 on #0a0c0f).
- muted is forbidden below 12px; use `text-tm-fg-2` for <12px secondary text.

## L2 hierarchy + density

- Stock detail main column: every block gets a consistent `<h2>` (title step).
  Three tiers via a `SectionBlock` wrapper:
  - Tier 1 (decision): LeanThesis, RichThesis.
  - Tier 2 (analysis): Signal Attribution, PriceChart, Fundamentals.
  - Tier 3 (reference): Catalysts, News, MarketContext, Sources, rendered under
    a lighter "Reference" grouping with a smaller heading + top rule.
- Picks table: row padding `py-1.5` -> `py-2.5`; driver/drag column mono -> sans;
  header row to label step.

## § 10 UI/UX Principles re-check

| # | Principle | Concrete decision (file) |
|---|-----------|--------------------------|
| 1 | Intent alignment | Tier-1 decision blocks first on stock detail (StockCardLayout main col order) |
| 2 | Cognitive load | One type scale (6 steps) replaces 8 ad-hoc sizes; mono only on numbers |
| 3 | Visibility of status | Unchanged (streaming/skeletons handled in #1 task); tier headings aid scanning |
| 4 | Forgiveness | Pure CSS/class change, fully reversible; no destructive action |
| 5 | Affordance | Same size = same role app-wide; HoverTip (instant) already standardizes tooltips |
| 6 | Design disappears | Readable floor (11px) + AA contrast means the eye stops fighting the text |
| 7 | No manual | Tier headings make the 10-block stock page self-navigating |
| 8 | Respects time | No latency change; faster visual parsing |
| 9 | No dark patterns | Contrast raised toward AA, not lowered; no hidden defaults |
| 10 | One primary action | Tier-1 (rating/action/thesis) visually dominates the reference tail |

## § Cross-cutting conventions audit

| Convention | Status |
|-----------|--------|
| i18n keys | No new copy beyond existing; any new section labels added to zh+en blocks |
| Font family | Inter Tight (sans) / Songti SC (zh titles) / JetBrains Mono (numeric only) preserved |
| Layout wrappers | Reuse existing `StockCardLayout` grid; add `SectionBlock` wrapper, no new page shell |
| Dark/light | Only `--tm-muted` token changes; light already AA (#6b7079); verify both |
| zh/en | Section headings already keyed; verify toggle still renders |
| Data locale fields | Untouched (no data shape change) |

## Verification

- `tsc --noEmit` clean.
- Manual: dark + light, zh + en, on /picks and a /stock/[ticker].
- No backend deploy (frontend auto-deploys on push).
