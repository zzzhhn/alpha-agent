# alpha-agent roadmap

Single-user, free-data, research-only quantitative equity rating engine. This file
is the ordered master plan; detail docs are linked per step.

Guiding principle (from the 2026-06-19 llm-council review,
`docs/_council-consolidation-review/FINAL_verdict.md`): **do not build more alpha
machinery right now.** The engine does not need more sophistication; it needs
causal memory, fewer silent drift paths, and fewer ways to lie to itself. So the
order below front-loads "prove the current product is honest and works" over
"add more signals/factors."

## Shipped recently

- **Append-only product ledger** (step 1, 2026-06-19) — migration V024
  (`research_run` + `rating_snapshot`); writer/reader `storage/product_ledger.py`
  (append-only, duplicate-complete guard, canonical = latest complete by
  finished_at); `ledger.record_daily_close` snapshots the canonical picks view
  via the shared `build_lean_view` (golden round-trip = byte-identical to what
  the user saw); wired best-effort + idempotent into `fast_intraday` full runs.
  No change to the live read path or signal numerics.
- **RSRS timing factor** (`signals/rsrs.py`) — weak-but-positive decorrelated tilt,
  small capped weight. Keep; re-judge by incremental forward contribution (step 7),
  not by IC cutoff.
- **Directional consistency** on picks (5d/1m/1y/all next-day hit-rate).
- **Dead-price-feed guard** — untradeable tickers dropped from default ranking;
  cron surfaces skipped tickers.

## Ordered plan (council ICE ranking)

### 1. Append-only product ledger  ✅ SHIPPED 2026-06-19
The engine has no causal memory of what it believed when. Build immutable
`research_run` + `rating_snapshot` tables recording, per market date, what was
emitted and what the user saw (composite, rank, tier, eligibility, coverage,
effective weights, price source + as-of), plus provenance (registry_hash,
weight_policy_id, tier_threshold_version, data_asof). No overwrites; corrections
are new run IDs. This is the prerequisite that makes honest L2, forward IC, drift
detection, adaptive-weight validation, and tier checks possible. Without it every
validation layer can silently recompute the past and fool us.
Detail: `docs/product-ledger-plan.md`.

### 2. Run health + abstention gates
Bad runs must not be treated as tradable truth. Gate each run on eligible-count,
stale-feed count, missing-price count, failed-signal count, benchmark availability,
BUY/SELL counts, sector concentration; mark failing runs non-tradable. L2 consumes
only `complete`, gated runs. Detail: in `docs/product-ledger-plan.md`.

### 3. Signal-registry consolidation
Replace the ~10 hand-maintained registration sites with ONE data-only manifest
(string import paths, explicit fields, no eager imports), derive all backend lists,
codegen the frontend mirrors (CI fails if stale), add lazy-import + invariant tests.
Detail (revised per council): `docs/signal-registry-consolidation-plan.md`.

### 4. Delete dead legacy + freeze discovery expansion
Prove `llm/_legacy/` unused via import graph, then delete it. Freeze new
LLM-factor / evolution / sandbox expansion until the ledger + L2 prove the current
product has forward value. Do not spend effort discovering exotic weak signals now.

### 5. Resolve the inert adaptive-weights subsystem
`backtest/adaptive_weights` computes EWMA-ICIR weights that nothing live consumes.
Inert is forbidden (false capability). Pick one: (a) research-only, explicitly
labelled not-live; (b) guarded activation `0.9*static_prior + 0.1*adaptive` with
min-sample, caps, nonneg, fallback, persisted effective weights; or (c) delete.
Do NOT flip EWMA-ICIR fully live on noisy free-data IC.

### 6. Minimal causal L2 forward paper-trading
On top of the ledger: long-only top-50, equal-weight, weekly rebalance, signal
after close D filled at D+1 close, 10 bps/side (report 5/20 sensitivity), benchmark
SPY (secondary RSP). Orders generated from a PRIOR immutable snapshot and persisted
before execution prices are consumed. Report gross+net+turnover+stale-count+
sector+beta+confidence bands. Held positions never silently dropped. This is the
honest "should the user trust the ratings" test. L3 real-money execution stays
deferred until L2 shows a forward edge. Detail: `docs/l2-paper-trading-plan.md`.

### 7. Prune signals by incremental forward contribution + tier validation
Only after the above: prune a signal only if low IC AND redundant-correlation AND
poor coverage/staleness AND high maintenance AND no forward/L2 contribution (never
a hard IC cutoff). Add monthly tier-monotonicity validation (BUY > OW > HOLD > UW >
SELL forward return; hit-rate + turnover by tier).

## Backlog / later (explicitly NOT now)

- L3 real-money live execution (broker API) — gated on L2 forward edge.
- GA-based factor mining as a second discovery engine. (RedNote note 5)
- Explicit money-management / position-sizing stage. (RedNote note 3 step 5)
- Research diagnostic: decile-spread / broad rank-weighted book to measure
  cross-sectional ranking alpha (separate from the user-facing top-50 product test).
