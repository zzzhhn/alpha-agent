# Project Learning Ledger

## 2026-08-09: Generated references are contracts, not decoration

- Route ownership must be resolved before visual work. The approved “Factors” reference belongs to `/alpha`; the older consolidation document describing `/factors` is superseded for this four-page redesign.
- A page is not aligned merely because the successful state resembles a mockup. Idle, loading, partial, unauthorized, and error states must preserve the same information architecture.
- Pixel imitation must not invent populated data. Match geometry and hierarchy with honest unknown states, then populate only from real APIs.
- For data-dense desktop workbenches, verify both the native reference viewport and a narrower desktop viewport. This iteration checks 1672 × 941 and 1440 × 900.
- Store native generated images separately from upscaled review copies, and record their actual pixel dimensions.

## 2026-08-09: Empty analytics need a cause and a recovery path

- A blank Holdings pane was not merely a styling defect. The new form had dropped an existing opt-in API parameter, so the correct fix joined request wiring, payload-cost disclosure, and an actionable empty state.
- Heavy evidence should not be silently enabled to make a screenshot look populated. Keep the efficient default, state the approximate cost, and tell the user exactly how to request the data.
- Validation rows should represent distinct robustness questions. Five convenient KPIs are not equivalent to OOS performance, walk-forward stability, cost sensitivity, concentration, and point-in-time data risk.
- Placeholder categories such as `Unknown` are data-quality states, not user-selectable business categories. Preserve them in results while removing them from filter controls.
- Queue and ledger height must be bounded by design. Pagination and single-row expansion make backlog size independent of page length.

## 2026-08-09: Refresh acceptance is not snapshot publication

- A GitHub Actions dispatch acknowledgement, a completed signal shard, and an immutable recommendation publication are separate states. Never collapse them into one green success label.
- ETA is presentation guidance only. When it elapses, the UI may enter a verification state, but success requires a correlated terminal publish record.
- Carry one `request_id` from the in-app dispatch through the workflow and publish audit so concurrent or scheduled jobs cannot settle the wrong user action.
- A same-market-date rerun is a valid compute outcome but an immutable-ledger no-op. Report it as `no_op_same_market_date`, including the retained run and market date.
- Canonical daily-close freshness follows the latest completed XNYS session plus price-date and health gates. Do not expire a healthy Friday snapshot solely because 24 wall-clock hours pass during a weekend or holiday.
- Keep the legacy live-row fallback's wall-clock guard. Canonical and non-canonical data have different freshness contracts and must be tested independently.
