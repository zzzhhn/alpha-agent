# Reference workspace refinement

Date: 2026-11-03. Scope: Guide, Data, Methodology and Settings.

## Design boundary

Use integrate-design to improve the existing workstation, not replace it. Keep the shell, cream/green palette, typography, TM controls, chapter/view taxonomy and existing account data. Improve the task canvas, reading density, navigation and truthful state mapping. No new UI dependency, chart package, polling, model run, database schema or investment behavior.

## Implemented

| Page | Friction | Refinement |
| --- | --- | --- |
| Guide | Long stacked articles, search confined to the current chapter | Existing six chapter tabs plus a bounded topic index and one readable article; full-guide bilingual search includes steps; clearing search restores the pre-search reading position |
| Data | Dense ticker wall, date clipping, coverage labelled as cache hit, all-or-nothing loading | Coverage summary and 16-item searchable/sector-filtered roster; paginated expression catalog; independent requests and retries; stale-response protection; close coverage labelled explicitly |
| Methodology | Long schema/operator/formula tables and mixed English labels | Search/category filters and ten-row pages; formula, source and signature details disclosed on demand; static definitions remain accessible when live requests fail; technical errors are secondary |
| Settings | All tools and destructive actions stacked; saved Kimi connection appeared as default OpenAI; testing required re-entering a saved key | Five purpose-based sections, editable connection plus saved-state inspector, server-metadata hydration, testing an unchanged saved connection without another save, explicit draft state, confirmed credential removal and separate account deletion |
| Settings details | Vault storage conflated with tested connectivity; unbounded history | BRAIN storage/test/unknown states separated; history uses five-row pages with confirmed supported-field rollback; watchlist uses eight-row pages; preferences localized |

No records are hidden by a hard truncation. Pagination preserves access to every loaded item. Settings history explicitly remains the latest 50 records returned by its existing API. Credentials are never populated from the server; only masked metadata is displayed. Changing a hosted provider/model/endpoint still requires the key under the existing save contract.

## Verification and evidence limits

- Actual components rendered in the existing shell at 1710×931, light Chinese, with matching inputs for before/after. Also checked English/dark Settings at 1440×900 and English Methodology at 900×900; neither body nor main horizontally overflowed.
- Guide: cross-chapter search, result selection and returning to the pre-search topic. Methodology: detail disclosure, last formula page and search resetting pagination. Data: roster page 2, ticker search, empty search and independent errors. Settings: draft persistence across tabs, rollback disabled while draft is dirty, history page 2, discard, credential-removal cancellation and typed deletion guard.
- Local visual harness blocks all non-GET requests. Settings uses explicitly synthetic masked connection/history metadata. No real credential save/test, rollback or account deletion was performed for QA. Existing watchlist mount synchronization was not redesigned.
- Public universe/sectors are genuine same-day archived responses: 568 tickers, 12 sector values. Coverage/catalog/source requests retain captured production HTTP 500, not invented healthy data. The Data comparison therefore demonstrates partial-failure recovery. Full live Data/catalog acceptance remains blocked by the separate backend incident.
- Guide content retains its declared 2026-09-08 version; this pass does not claim a complete current-feature manual rewrite.
- Focused checks: guide navigation and saved-connection matching (8 tests), TypeScript, changed-file lint, design-system/token audit. Production build and release outcome are recorded below.
- User visual approval remains separate from implementation, browser verification and release.

## Production incident observed during review

At 13:26 UTC, both frontend same-origin and backend health/data paths returned HTTP 500 `FUNCTION_INVOCATION_FAILED`. Runtime stderr records ENOSPC while Vercel cold-start dependency installation writes litellm and extracts pyarrow. The existing backend deployment was marked READY despite a 463.77 MB bundle triggering dependency optimization. The UI changes were not deployed at that time. No database corruption or Neon quota cause is established. A separate bounded backend packaging repair was proposed to the user; no runtime configuration was altered in this UI change.

## Evidence files

Local delivery directory: `/Users/a22309/.codex/visualizations/2026/07/27/019fa455-20bf-7ca3-b1c9-94534e8bb207/`.

Pairs: `guide-comparison-before-20261103.jpg` / `guide-after-20261103.jpg`, `data-comparison-before-20261103.jpg` / `data-after-20261103.jpg`, `methodology-comparison-before-20261103.jpg` / `methodology-after-20261103.jpg`, `settings-comparison-before-20261103.jpg` / `settings-after-20261103.jpg`. Methodology pair uses the same Backtest view, with one formula opened after refinement to show disclosure behavior.

## Release

Production build passed, including TypeScript/lint and the design-system/token audit. Eight focused tests passed. One existing hook-dependency warning in unrelated RecentRunsTable remains. Release verification is pending. Backend incident is independent of these frontend files and must not be described as fixed by a UI deployment.
