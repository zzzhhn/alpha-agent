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

## 2026-08-09: Paginating rows must not fragment a research run

- A manual BRAIN run requesting 20 candidates did not lose eight rows. A later scheduled run inserted eight newer rows, so a global 20-row page displayed eight new rows plus only twelve from the manual run.
- Time dividers do not create ownership. If users reason about results by run, the database, API, selection state, and pagination must all use a durable run identifier.
- Long-running research funnels need distinct counts for requested, generated, screened, simulated, persisted, and accepted candidates. Reusing one number across stages makes normal filtering look like data loss.
- Optional LLM screening must report bypass and parse failure honestly. Falling back to all candidates preserves availability but is not a successful screen.

## 2026-08-10: Separate cheap search breadth from expensive simulation depth

- Expression generation and real BRAIN simulation consume different resources. A useful composer exposes both budgets instead of labelling both as “candidate count.”
- Oversampling only creates value when the run records generated, selected, simulated, and persisted counts separately. Otherwise a logic screen can look efficient while silently shrinking the requested research budget.
- Reusing a configuration must create a child run, not mutate history. This preserves comparison and makes parameter changes auditable.
- Historical PnL retrieval is independent I/O, so a small concurrency cap can reduce mining warm-up without parallelizing the stateful simulation and diversity-gating loop.
- Workflow advice should be derived from visible run counts. It may recommend recovery, broader generation, family rotation, or human review, but it must not auto-submit candidates.

## 2026-08-10: Historical deduplication is steering, not a success condition

- The options template has a finite set of structurally distinct variants. A generic signature that erases every digit can collapse economically different option tenors into the same historical structure and eventually filter an explicit options run to zero candidates.
- The earlier availability fix allowed an explicit family request to backfill historical variants. RUN #64 showed the cost: five excellent options-skew variants all failed self-correlation, with adjusted correlation around 0.91 to 0.98. Discovery must now stop at exhaustion; historical replay belongs only in an explicit robustness/retest mode.
- A requested run that generates zero candidates is failed, not completed. Persist the zero funnel and the generation reason, submit no BRAIN simulations, and show a recovery message instead of a generic empty table.

## 2026-08-10: Performance quality is not signal novelty

- A high BRAIN grade, Sharpe, and Fitness can coexist with near-zero marginal portfolio contribution. Product verdicts must show performance quality and novelty separately.
- A user-facing family name must match the generator's real search space. “Options” cannot route only to one PCR-gated call-put IV-skew template when the catalogue and code already support term structure, IV dynamics, variance risk premium, PCR dynamics, and breakeven-forward mechanisms.
- Dataset ordering is part of search correctness. A global field limit exhausted before option8 and option9, so an options run must query those catalogues first rather than claim broad exploration from a static six-field vocabulary.
- Logic ranking alone does not guarantee diversity. Before expensive simulations, select one candidate per economic mechanism before taking a second candidate from any mechanism.

## 2026-08-12: Novelty without an alpha anchor is weak diversification

- RUN #66 solved the duplicate-skew problem but rejected all five independent mechanisms before self-correlation. Diversity is a constraint on a viable signal, not a substitute for signal strength.
- A five-simulation options budget cannot treat every hypothesis as equally mature. Allocate first to a proven anchor plus orthogonal residuals, then to measured near-misses, and leave speculative fields for larger research rounds.
- Do not randomize expression sign, liquidity gate, universe, delay, neutralization, and decay in the same first-pass simulation. That confounds mechanism quality with settings quality and prevents the run history from teaching the generator.
- Preserve the economic magnitude before cross-sectional ranking. `rank(HV)-rank(IV)` can collapse into a static book; normalize `IV-HV` first and rank the resulting spread.
- Option channels have different money signs. Call-IV increases, put-IV increases, call-put skew, PCR changes, and IV term slope must be encoded as distinct hypotheses rather than pooled fields with random reversal.

## 2026-08-12: Secret transport whitespace is part of the dispatch contract

- A valid GitHub token can still fail before reaching GitHub when CLI stdin adds transport whitespace and the backend copies it directly into `Authorization`.
- Normalize secret-backed header values at the point of use, not only in the deployment command.
- Protocol exceptions may echo the rejected header value. Durable run ledgers and user-visible diagnostics must retain the exception class while discarding the raw message.

## 2026-08-13: Missing self-correlation is a workflow state, not a neutral value

- RUN #72 produced two GOOD alphas whose official self-correlation cells appeared as pending. Both had already failed `CONCENTRATED_WEIGHT` and `LOW_SUB_UNIVERSE_SHARPE`, so the main workflow intentionally stopped before the self-correlation request.
- Grade and submission eligibility are different axes. Preserve high-grade rejected candidates as research evidence and perform a small, sequential post-run self-correlation enrichment instead of spending this API budget on every failed simulation.

## 2026-08-13: Mechanism labels are not behavioral diversity

- RUN #73 spent three of five simulations on syntactically independent options mechanisms that were too weak, while both strong anchor-plus-residual formulas remained dominated by the same PCR-gated call-minus-put IV core and reached official self-correlation of 0.76 and 0.85.
- A simulation budget is a ceiling, not a quota. Do not backfill low-confidence candidates merely to consume it. Rank by field coverage, concentration risk, outcome alignment, historical mechanism posterior, and behavioral novelty before making expensive BRAIN calls.
- Scaling a second leg into the anchor's units is not residualization. Behavioral novelty must be measured from signal or return paths, not inferred from different operators, tenors, or mechanism labels.
- BRAIN's official hard threshold is `0.70`. An internal `0.65` level is useful as a crowding warning, but using it as a rejection threshold silently discards officially eligible candidates without changing their standalone Sharpe or Fitness.
- The implemented P0 path now treats the BRAIN simulation budget as a ceiling, ranks options candidates with official field coverage plus measured mechanism outcomes, and refuses to backfill low-evidence candidates merely to fill the requested count.
- A catalogue outage and a field missing from a successfully loaded catalogue are different states. The former retains a neutral prior and marks the screen partial; the latter receives no fabricated coverage credit.
- Environment-variable metadata, a Ready deployment, an active workflow, and a successful authenticated dispatch are separate checks. The first three cannot replace the final user-path retry.

## 2026-08-13: A small proxy must earn the right to steer expensive simulations

- Options history is imbalanced by mechanism and simulation settings, so an in-sample fit can mostly rediscover the dominant configuration rather than generalize to a new hypothesis. Split chronologically and compare against a constant baseline before exposing a prediction.
- A personal project does not need RL or MCTS to learn from 100 to 200 observations. A regularized NumPy model plus hierarchical context posterior is cheaper, auditable, and safe to deactivate when the evidence is weak.
- Separate failure feedback by cause. Tight truncation can address repeated concentration and extra decay can address turnover, while low sub-universe Sharpe is a stability warning and does not justify shrinking the universe automatically.
- Persist the research contract with every simulated candidate. Paper source, target outcome, field mapping, current coverage, settings context, alternative explanations, and falsification rules must survive page refreshes and future code changes.
- `1 − adjusted self-correlation²` is only a diversification proxy. Naming it marginal contribution would overstate the evidence unless a real portfolio-level incremental-return regression is available.

## 2026-08-14: Field coverage is not economic-semantic coverage

- A field ID found in option8 or option9 proves availability, not that it reproduces a paper's variable. Ordinary `pcr_oi` cannot stand in for buyer-initiated opening option volume, and single-stock IV minus HV cannot silently inherit aggregate model-free VRP evidence.
- Pair call and put, breakeven and forward, or implied and realized volatility by shared tenor or moneyness. Positional list pairing can create a legal expression with the wrong economic construction.
- Failure counters may overlap on one BRAIN simulation. Do not sum concentration and sub-universe failures as if they were independent attempts when deciding that a mechanism is historically exhausted.
- Semantic audit, target alignment, and missing required fields belong in the persisted research evidence and the expanded-row UI. A `mapped=100%` badge alone is not decision evidence.

## 2026-08-14: Recommendation metrics need an object and a horizon

- Per-name 1-day direction agreement, 5-day calibrated confidence, and 5/20/60-day ranked-basket evidence answer different questions. A generic “hit rate” label makes them appear interchangeable when they are not.
- Show long and short sleeves separately before the long-short spread. A positive spread can otherwise conceal market drift or a failing short leg.
- Compare the fixed 5, 20, and 60-day horizons in parallel and keep sample counts visible. Do not choose the best-looking horizon after observing the data.
- A long-short quintile spread is dollar-directional evidence, not automatically market-beta neutral. Use precise labels unless an explicit beta hedge is measured.

## 2026-08-14: Persist generated candidates before optional screening

- A run-level `generated=20, simulated=0` aggregate cannot explain which expressions were withheld or why. Persist every generated expression before an optional LLM or deterministic screen, then update the same row through selected, withheld, simulated, or simulation-error states.
- LLM timeout, parse/provider failure, weak research evidence, and official BRAIN simulation failure are different events. Store a safe technical status and exact decision reason instead of letting one empty results table represent all four.
- A successful Vercel deployment does not update a GitHub Actions worker when workflow dispatch checks out `main`. Merge worker code and migrations to the dispatched ref before claiming the new mining workflow is live.

## 2026-08-14: Reasoning-model screens need latency-aware call boundaries

- A generic 60-second classification timeout was the wrong boundary for Kimi's reasoning call. Four serial batches repeated the model startup cost, and retrying the first batch consumed the global budget before later candidates were attempted.
- Score the generated pool in one call when the provider's dominant cost is reasoning startup. Keep an evidence-based 240-second boundary below the client's read timeout, and do not synchronously replay a slow request.
- A technical timeout still falls back to the shared deterministic evidence screen. Partial usable scores remain valid, and provider latency never becomes a BRAIN simulation failure.
- Persist sanitized provider, model, elapsed time, call mode, pool size, scored count, and error class/status. Never persist raw headers, credentials, response bodies, or exception messages that may echo them.

## 2026-08-24: A design system is a migration contract, not a component gallery

- A reusable component only becomes canonical when the production component, a `/reference` specimen, operating semantics, and real route adoption all agree. A visually convincing gallery alone does not reduce product inconsistency.
- Inventory raw controls by interaction role before replacing them. A selectable data row, icon action, exclusive toggle, and primary mutation may all use `<button>`, but they should not collapse into one visual treatment.
- Control density is a small fixed scale. The Topbar exposed 22 and 25 px local variants beside the 24, 28, and 32 px workstation scale; moving locale, theme, and filter choices to one radio-semantic toggle group removed both geometry drift and keyboard inconsistency.
- Historical and compatibility components should alias canonical primitives before deletion. This lets route migration proceed in bounded batches without breaking every consumer at once.
- Design governance must be executable: the sidebar reference, migration ledger, cross-cutting conventions audit, dark/light and zh/en browser checks, and an explicit exception process are part of the product source of truth.
- Accessibility contracts belong inside the primitive. Table captions, dialog focus entry and restoration, disclosure `aria-expanded`, and radio-group keyboard behavior should not depend on each route remembering the same implementation details.
- Canonical chart tokens become useful only after a production chart consumes them. A token specimen plus real equity, drawdown, and walk-forward adoption is stronger evidence than a palette page alone.
