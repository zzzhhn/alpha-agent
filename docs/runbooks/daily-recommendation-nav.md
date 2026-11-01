# Daily recommendation NAV

## Scope and accounting

The two existing continuous L2 books remain separate from personal `sim_`
accounts. No broker connection, live trades, automatic proposal approval or
strategy replacement is introduced. The existing Top-50/weekly target policy
and 10 bps per-side assumed comprehensive execution cost remain frozen.

`l2_cycle` now values already executed shares every XNYS session, even without
a rebalance. It catches up at most 65 sessions per call, with one bounded price
read and batch inserts. Cash and quantities do not change during valuation;
transaction costs are charged only on simulated fills. `last_fill_date` remains
the execution date; `last_valuation_date` is reported separately. Before the
next rebalance, marks through the preceding session prevent double-counting
multi-day returns. Repeated invocations do not repeat costs or marks.

No new database table, migration, feed subscription or polling schedule is
needed. Two daily books add about 504 small rows/year, using existing indexes.
The existing after-close `l2_cycle` job advances them after recommendation
publication. Missing prices carry the previous mark with an explicit stale
count, never silently disappearing. The chart gaps stale/missing observations.

## Comparison contract

- Start capital is 100. Do not renormalize after the first fee and erase it.
- Strategy NAV includes all actual simulated entry/rebalance costs.
- SPY/RSP buy-and-hold begins at the first executed close, including the same
  per-side entry-cost assumption. Cash earns no interest.
- 5/21-session returns require every daily mark in the window. Missing means
  unavailable, not zero. These are held-portfolio returns, not hit rates.
- Historical rebalance-only gaps remain visible. Recovering the market value
  of already held shares does not recreate missed decisions or executions.
- Provider-adjusted closes are not a full corporate-action ledger; taxes,
  brokerage fills and cash interest are not modeled. Fees are assumptions.
- Observed drawdown is incomplete where historic daily marks are absent.
- Repeated use of a policy's historical performance is not an independent test
  of alpha. Profitability remains unproven and should be judged prospectively.

## Interface and design review

Use existing `TmPane`, `TmTable`, `SegmentedTabs` and chart tokens. The new
`RecommendationNavChart` is registered in `/reference`. No new design dialect.
The evidence block is available on Today Recommendations and the paper page.

| Principle | Implementation |
| --- | --- |
| Intent alignment | Net return and benchmark use the same origin and date range. |
| Cognitive load | One curve with four named series; two explicit recent windows. |
| Visible state | Loading/error/retry and stale/gap status stay in the evidence pane. |
| Forgiveness | Read-only research pane; it never places personal orders. |
| Affordance | Existing segmented tabs and buttons, keyboard semantics retained. |
| Design disappears | Existing workstation geometry and chart tokens. |
| No manual needed | Separate automatic book from personal simulation in labels. |
| Respect time | Batch daily writes, bounded reads, no UI-triggered compute. |
| Transparent defaults | Cost, weekly cadence and unmodeled items stated. |
| Primary action | Evidence stays secondary to the existing page action. |

| Cross-cutting convention | Decision |
| --- | --- |
| i18n and values | Chinese/English names; explicit trading-day windows and USD costs. |
| Font and chart labels | Existing mono/body styles and 12px chart token floor. |
| Wrappers and sidebar | Existing picks/paper routes and panes; no new navigation item. |
| Themes and motion | Semantic tokens, no animation or smoothed interpolation. |
| Accessibility | Named chart, text summary, semantic table, keyboard tabs. |

Implementation and browser verification receipts are recorded after production
deployment; source checks alone do not establish visual acceptance.
