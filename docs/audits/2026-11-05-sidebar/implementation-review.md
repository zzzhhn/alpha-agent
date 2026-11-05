# Committed implementation cross-review

Scope: one focused static correctness pass over `e4a53c4..1964463` (`285e3d1`, `1964463`). No browser, source edits, build, dependency install, credentials or execution requests. Only this report is owned by the reviewer. Current implementation was read directly; prior production findings are not treated as verification of these fixes.

## Finding

### P2: Refresh does not refresh an off-page selected run's ledger

Exact changed lines:

- `frontend/src/components/brain/BrainMiningPanel.tsx:1732`: the directory refresh requests only the current `runsPage`.
- `frontend/src/components/brain/BrainMiningPanel.tsx:1791`: the selected snapshot is refreshed only when the selected ID appears in that directory response.
- `frontend/src/components/brain/BrainMiningPanel.tsx:1861`: the ledger falls back to the retained selected snapshot when that run is off-page.
- `frontend/src/components/brain/BrainMiningPanel.tsx:1899`: Refresh invokes `loadRuns()` plus the result query, not a selected-run ledger refresh.

Source-level reproduction:

1. Select runA from directory page1.
2. Page the directory to page2 without changing the selected run. Retaining runA/results is intentional.
3. Let runA status/counts change on the backend.
4. Select Refresh while still on page2.

The result query is refreshed for runA, but the directory request fetches page2 only. runA's retained ledger/status/funnel can therefore stay at its pre-change snapshot indefinitely, despite an apparently completed refresh and potentially updated result rows. The new pagination/snapshot retention introduces this mixed-freshness state. It requires a real server-side update to the off-page run; this was not reproduced in a browser or by generating mining work.

Smallest compatible correction: refresh the selected run's record as well, using a bounded selected-page/detail request, and replace its snapshot when found. If avoiding that read, explicitly mark the retained off-page ledger as not refreshed and scope the refresh label to the directory page/results. Do not silently label retained metadata current.

Suggested focused verification: controlled component/API fixture with two directory pages; selectA/page-away, change A's status/counts in the fixture, refresh, assert either updated A ledger or explicit retained/stale signage and consistent results.

## Reviewed contracts with no additional confirmed regression

- Alpha saves and compares use `alphaRunConfig(evidenceValidation)`; the hook copies primitive validation fields at submission/rerun. Subsequent draft objects cannot mutate the stored snapshot. Input and validation differences produce the unverified-draft notice. Legacy history now explicitly normalizes to SP500 without rewriting the saved record.
- Backtest and Report gate numeric execution as well as exposing field errors. Bounds match backend `FactorSpec.lookback`5–252, sleeve fractions1–50% and transaction cost0–200bps; integer lookback is enforced. Hidden advanced numeric errors have a discoverable summary.
- The BRAIN runs API already supports `offset`; the added optional third wrapper argument preserves the existing second `ApiGetOptions` position. Request sequence checks discard older page responses. Mining start/completion intentionally return the directory to page1. Selection does not silently jump on ordinary directory paging.
- Shared menu sizing now measures at its final width, uses actual content height and keeps an active option in the local scroller. Menu Escape stops propagation and the modal hook ignores handled events. These source changes address the observed detached-menu/menu-to-parent Escape path.
- Screener lookback step1 is compatible with the252 endpoint.

## Evidence limits / focused runtime checks

No fresh runtime or test execution was performed in this static lane. Existing pure-helper tests prove numeric mappings/math, not React focus order, immutable async handoff or production release.

Primary should retain focused runtime checks for menu Tab/Shift+Tab inside a modal, upward long/short menu geometry, and the committed Alpha save/compare behavior under edited drafts. The modal hook's `defaultPrevented` check alone is not evidence of general multiple-modal stack ordering; no new nested-dialog defect is asserted without an actual affected nesting path. General portal-stack redesign is outside this pass.

No other blocking correctness issue was confirmed in the reviewed diff.
