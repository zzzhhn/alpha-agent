# Research routes interaction audit

Inspection: 2026-11-05 continuing into 2026-11-06, production `https://alpha.bobbyzhong.com`. Routes: `/alpha`, `/backtest`, `/screener`, `/report`. Source baseline: PR73 audit worktree, commit `e4a53c4c531c96d9df8e136b0fb2c6554f24e3d5`.

## Result and boundary

64 grouped control/state receipts: **33 tested-pass, 8 tested-fail, 23 blocked**. These are control-family statuses, not 64 distinct buttons and not eight independent product defects. The eight failing receipts map to six defect families below; number-range failures appear on three controls.

The browser pass is complete as a bounded safe audit, **not an “every UI control passed” claim**. Completed-result controls were unavailable without computation; several safe lower-priority paths were not exercised before the requested prompt release. Exact instances and gaps are in `research-coverage.json`.

Keep the approved TM terminal identity, shared shell, desktop density and truthful unknown values. Refine interaction/recovery locally. Integrate-design, the master system and 2026-11-03 Alpha/research-workspace records guided the audit. No source implementation edits in this lane. Primary is integrating fixes separately; this report does not claim those fixes are deployed or browser-verified.

Baseline: existing Chrome 用户1 instance, one task-owned replacement tab `1395914578`, **1710 × 875**, Chinese dark. All four idle routes also received a brief English/light visual pass. Root/document width stayed1710 on those frames, with no page-level horizontal overflow. Chinese dark restored before closure. The four layouts retain the TM shell, clear composer/evidence relationship and honest pre-run dashes.

Resource preflight remained constrained: memory pressure2, swap11.0GiB, free disk19.07GiB. No parallel build, local server, dependency install or additional browser instance. The previous agent's opaque tab could not transfer across browser sessions; after confirmed closure, one replacement tab was opened in the same Chrome instance and later closed. User-owned tabs were preserved.

## Confirmed production interaction findings

### P1 R-B01: Legacy Alpha history restores a universe different from the visible selector

Steps: `/alpha` → 历史 → existing 2026-05-20 Earnings Yield history entry, originally CSI500.

Actual: header becomes `股票池 CSI500`, while the native selector displays S&P500 with only SP500/custom options. The draft therefore contains an unsupported legacy value which the visible select does not represent. No computation was started.

Expected: normalize unavailable historical universes to the supported universe, with concise notice when changed. Relevant source: `alpha/page.tsx:handleHistorySelect`. Primary was notified and reported a working-tree normalization fix; no production recheck.

![Alpha legacy history universe mismatch](/Users/a22309/.codex/visualizations/2026/07/27/019fa455-20bf-7ca3-b1c9-94534e8bb207/sidebar-audit-research/alpha-history-universe.jpg)

### P2 R-B02: Numeric min/max do not gate Backtest or Report execution buttons

Steps: Backtest → load existing Volume Z-Score20d → enter top%=99 and cost=-1. Separately Report → load saved Volume Z-Score20d → enter cost999.

Actual: values remain visible, including `成本 -1 bps`; Run/Generate remain enabled with no local range error. Buttons were **not clicked**. Native `min/max` validity is not automatically enforced by these independent button handlers.

Expected: actionable inline error and disabled execution until valid, or a consistent bounded-entry policy. Alpha number fields already clamp99→50,999→200,0→5,-2→0. Small fix: route-level numeric validation matching the real API bounds; do not silently alter backend policy.

Relevant sources: `BacktestFormSticky.tsx`, `ReportComposer.tsx`, `TmField.tsx:TmNumberInput`. Primary reported bounded working-tree validation changes; no deployment/recheck.

![Backtest accepts out-of-range draft](/Users/a22309/.codex/visualizations/2026/07/27/019fa455-20bf-7ca3-b1c9-94534e8bb207/sidebar-audit-research/backtest-invalid-range.jpg)

Report evidence: `report-invalid-range.jpg`.

### P2 R-B03: Short upward menus detach from their trigger

Steps: Screener → 合成方式 at the lower left of the desktop setup → open menu.

Measured actual: trigger top669/bottom697; menu top377/bottom467, height90. A **202px empty gap** separates menu bottom and trigger top. Selection works, but the menu appears over unrelated factor rows.

Expected: upward menu bottom adjacent to trigger, using actual rendered height, with viewport bounds. Relevant source: `TmSelectMenu.tsx:place`, fixed288px assumption. Primary owns the shared fix.

![Detached upward menu](/Users/a22309/.codex/visualizations/2026/07/27/019fa455-20bf-7ca3-b1c9-94534e8bb207/sidebar-audit-research/screener-upward-menu.jpg)

### P2 R-B04: Escape from a menu closes the enclosing Report library

Steps: Report → 从示例／因子库载入 → 来源 menu → press Escape once.

Actual: both listbox and enclosing dialog close; DOM counts become0/0 and focus returns to the outer library trigger. Expected: close only the topmost menu, preserving the library and its search context. Relevant source: shared menu Escape propagation and modal key handler. Primary owns the shared fix.

Evidence: `report-escape-closes-dialog.jpg` is the post-close state; the decisive evidence is the before/after AX/DOM interaction receipt, not that screenshot alone.

### P2 R-B05: 252-day preset and native slider disagree

Steps: Screener → click252天.

Actual: selected preset/output says252天 while native range/AX value is250. Range is min10/max252/step10, so the browser sanitizes252 to250; keyboard End also reaches250. Expected: selected preset, announced value and keyboard maximum agree. Small fix: compatible step/endpoint policy, for example step1 if preserving252 is required.

![Screener252 preset mismatch](/Users/a22309/.codex/visualizations/2026/07/27/019fa455-20bf-7ca3-b1c9-94534e8bb207/sidebar-audit-research/screener-252-slider.jpg)

### P2 R-B06: Alpha exposes a custom-universe choice that is metadata only

Browser: custom is selectable and no membership/ticker-definition control appears. Source contract, not a paid runtime experiment: `interactive.py:310` forwards universe only to the LLM prompt; line352 calls smoke with expression/lookback only. `scan/smoke.py:309–312` always makes its synthetic20-ticker panel, and `factor_backtest.py:774` always loads the cached panel without branching on `spec.universe`.

Expected: expose only supported SP500, consistent with Backtest, or explicitly disable unsupported membership with a concise reason. Legacy backend docstring ticker counts are not treated as current panel coverage evidence. Primary accepted the SP500-only contract; no translation was invoked.

## High-confidence source-only traceability finding

### P1 R-S01: Alpha saves performance without the completed run's reproducible settings

`alpha/page.tsx:151` calls `addToZoo` with headline metrics but no direction, neutralization, benchmark, mode, sleeve fractions or transaction cost. Consumers `factor-zoo.ts:readConfig` and `BacktestFormSticky.tsx:loadFromZoo` use these fields/defaults. Meanwhile draft validation remains editable after completion and `handleOpenBacktest` pairs the old translated expression with latest draft validation.

Expected: immutable completed-run settings remain bound to metrics, save and comparison; changes become an explicitly unverified draft. Simply appending **current** draft values to saved metrics would not fix stale identity. Primary reported completed-run snapshot semantics and a dirty-draft indicator implemented in working tree.

Evidence boundary: no result generation, save or compare handoff was executed. This is a source-traced defect, not browser reproduction.

## Positive interaction evidence

- Alpha: example search/no-match, Cash Buffer draft and parameter load, history Escape/focus return, hypothesis clearing/disabled action, all supported visible direction/neutralization/benchmark choices and number clamps.
- Backtest: saved Volume factor loads without running; advanced disclosure mounts/unmounts, direction/benchmark/mode and both checkboxes respond; reset restores original blank/default form. Unknown `ts_means(retruns,20)` shows `ts_mean`/`returns` suggestions and disables Run.
- Screener: all three loaded factor selectors tested, including Space on Earnings Yield. Search hides rows without losing selection. All three combination methods, custom weight2.5, both neutralization options, all11 real sector options, remove/clear, excluded-ticker uppercase/dedup, all date/count/lookback/cap preset buttons tested. Defaults restored.
- Report: both source types, saved Volume and historical Cash Buffer drafts, source search/full-loaded matches/no-match, first/last library page and disabled boundaries, all direction/neutralization/benchmark options, name/expression editing. Loading drafts does not fabricate results or compute.
- Numeric keyboard focus is **not a defect**: observed2px accent outline on keyboard-focused number input. The global focus rule supplies the indicator despite wrapper-class concerns.
- English/light idle layouts were viewed on all four routes, then Chinese/dark restored. Representative captures are `*-idle-light-en.jpg`; dark baselines are `*-idle-dark.jpg`.

## Honest gaps and next verification

No LLM, backtest, report generation, screener run, save, pin, undo/deletion, settings save, auth change or synthetic data injection occurred. No naturally existing completed result survived on these route instances. Therefore result charts, AST/detail analytics, comparison, report deep analysis, CSV/HTML/print and result-ledger operations remain blocked, not passed. No injected network failures or mobile/narrow acceptance.

Safe paths left unexercised are explicit receipts: bottom%/lookback field editing and the single-option universe control, example/report close icons, autosave tooltip hover, count-slider direct drag/key path, history outside-click, and the ledger's separate Reopen trigger. Only3 factors were loaded, so Screener5-row pagination was absent. Repeated example rows were sampled by equivalent component, not all10 clicked.

Next owner: primary integrates and verifies fixes; Advanced continues in a new task tab in the same existing Chrome instance. This lane's task tab has been closed. Deployed-path verification and user visual approval remain separate.

## Context provenance

Memory was used only to route the audit and preserve the distinction between static findings and current UI acceptance. Current source/design records govern the findings. Registry: `MEMORY.md:237–274`; prior audit rollout IDs `01a19787-0267-7262-aeac-788779f3eea7`, `01a19787-091b-7e03-8a32-dcdc24a76e49`, `01a19787-1102-7ba3-8a21-cd513e942127`.

