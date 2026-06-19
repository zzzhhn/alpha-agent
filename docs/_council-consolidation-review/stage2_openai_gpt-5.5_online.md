## 1. Highest-confidence convergence across multiple reviews

### A. Registry consolidation is real and worth doing.
Reviews **A, B, C, and partly D** agree the current problem is metadata/list drift, not duplicated signal logic. Adding RSRS touching weights, horizons, core sets, crons, health routes, CLI, and frontend mirrors is exactly the smell.

**High-confidence conclusion:** build a single registry-derived metadata source.

But the consensus is **not** “central registry imports all signals.” The real consensus from A/B/C is:

> Central **data-only** manifest, string import paths, lazy compute imports, generated frontend metadata.

That is the correct architecture.

---

### B. Decorator self-registration is the wrong fit here.
Reviews **A, B, C** converge strongly against decorators.

Reason: decorator registration only works after importing every signal module. That defeats the main constraint: serverless/cold-start/import hygiene.

**Correct reading:**

```python
SignalMeta(
    name="rsrs",
    module_path="alpha_agent.signals.rsrs",
    compute_fn="compute",
    ...
)
```

not:

```python
@register_signal(...)
def compute(...):
    ...
```

The latter makes discovery dependent on import order and eager imports.

---

### C. Frontend metadata should be generated, not runtime-fetched.
Reviews **A, B, C, D** all converge here.

Runtime `/api/_signal_registry` is useful for debug/introspection, not for normal UI rendering.

**Best answer:** generate a checked-in TS artifact, fail CI on drift.

---

### D. L2 / forward paper-trading is necessary, but only if causal.
Reviews **A, B, C** converge that IC is insufficient. IC tells you whether ranks correlate with later returns. It does **not** prove the actual user-facing product survives:

- stale feeds
- eligibility filters
- tier thresholds
- execution lag
- turnover
- costs
- missing data
- universe drift
- benchmark mismatch

So L2 is directionally right.

But all serious reviews agree the heart of L2 is not the portfolio simulator; it is the **immutable point-in-time decision ledger**.

---

### E. Same-close execution is invalid with this data stack.
Reviews **A, B, C** converge that if signals use close `D`, you cannot also fill at close `D`.

For this system, use one of:

- signal after close `D`, fill next trading day open;
- signal after close `D`, fill next trading day close.

I prefer **next-day close** for simplicity/robustness with free daily data unless open prices are already trustworthy in your DB.

---

### F. Costs and turnover must be explicit and punitive.
Reviews **A, B, C, D** agree costs cannot be ignored. Given weak ICs and free data, gross-only curves are basically propaganda.

Minimum:

- long-only: 5–10 bps per side;
- long-short: 10–20 bps per side plus borrow/short penalty if modeled;
- always report gross and net;
- always report turnover.

---

### G. Dead feeds / delistings / stale prices are a major paper-trading lie.
Reviews **A, B, C, D** converge here.

Correct rule: a held ticker cannot disappear from the book just because yfinance stops returning clean data.

Need explicit handling:

- carry stale price briefly with flag;
- force exit after threshold;
- penalize unknown exits;
- never silently drop positions.

---

### H. Current methodology is overbuilt relative to data quality.
Reviews **B, C, D** converge that LLM factor proposal/evolution/sandboxing and inert adaptive weighting are over-complex for a single-user, free-data, weak-edge engine.

The exact prescriptions differ, but the convergence is:

> Stop expanding machinery until you have a forward truth layer.

---

## 2. Wrong, overstated, or misread claims

## Review A

### Mostly correct, but over-scoped the first L2 schema.
A’s schema is good architecturally, but too heavy for the first implementation.

For this context, you do **not** need seven tables on day one. You need:

1. `research_run`
2. `rating_snapshot`
3. `l2_strategy`
4. `l2_order`
5. `l2_equity_daily`

`signal_snapshot`, `l2_fill`, and `l2_position_daily` are useful, but can be phase-two unless you already have the storage discipline.

The minimum truth-preserving object is the immutable rating snapshot. Without that, everything else lies. With that, you can add fill/position detail later.

---

### A underplays the sequencing advantage of deleting dead code first.
A says delete legacy after migration/deploy cycle. B/C are more right: delete obvious dead paths **before** registry migration if import graph proves they are dead.

Otherwise you risk:

- wiring dead modules into the new registry;
- preserving legacy behavior in snapshots;
- making tests defend code you intend to remove.

Correct sequence:

1. prove unused;
2. tag branch;
3. delete;
4. then registry.

---

### A’s “top 50/75 long-only first” is user-aligned but not necessarily statistically best.
For a user-facing trust portfolio, long-only top basket is intuitive.

But B is right that the IC lives in broad cross-sectional ranks. A concentrated top basket can be high variance and slow to validate.

Correct split:

- **Primary user book:** long-only top basket vs SPY/RSP.
- **Primary research diagnostic:** broad rank-weighted spread / decile spread / beta-neutral book.

Do not make only one of these carry all epistemic weight.

---

## Review B

### Correct that the ledger is the real prerequisite.
This is the strongest part of B.

The ledger beats both proposals as originally scoped because it enables:

- forward IC;
- L2;
- drift detection;
- forensic debugging;
- user trust.

This should be promoted above “portfolio simulator.”

---

### Overstated: “top-N equal-weight should not be primary.”
This depends on the question.

If the question is **does the rating system contain cross-sectional signal?**, B is right: broad rank-weighted / decile spread is better.

If the question is **should the single user trust the actual output?**, top-N long-only is primary because it maps to plausible user behavior.

So B’s claim is wrong only if treated universally.

Correct framing:

| Question | Primary test |
|---|---|
| Is there ranking alpha? | broad rank/decile spread, beta/sector controlled |
| Is the product useful to user? | long-only top basket vs SPY/RSP |
| Is short-side signal real? | separate long-short diagnostic |

---

### Overstated: “vol-scaled/equal-risk, not equal-dollar.”
Vol scaling is useful, but it introduces another model layer and another failure mode.

For first L2, equal-weight is more auditable.

Better sequence:

1. equal-weight canonical;
2. equal-weight with turnover buffer;
3. inverse-vol diagnostic only after the ledger works.

The first portfolio should be stupid on purpose.

---

### Good but incomplete: adaptive weights.
B correctly flags inert adaptive weights as liability.

But “wire or delete” is too binary. There is a third path:

> keep calculating adaptive weights, but label them explicitly as research-only and exclude from live fusion until a pre-registered forward criterion is met.

That is acceptable if the UI/API cannot imply they are active.

---

## Review C

### Correct on registry lazy-load.
C’s registry advice is clean and correct.

---

### Overstated: “delete adaptive weights.”
C says permanently delete adaptive weights. That is too aggressive.

The problem is not that adaptive weighting can never help. The problem is that it is currently **computed but ignored**, which creates epistemic and operational debt.

Correct action:

- either wire behind strict guardrails;
- or freeze/relabel as research-only;
- or delete if no owner/test/use-case.

But “equal-weight always wins in noisy environments” is too broad. Equal weighting is a strong baseline, not a theorem.

---

### Overstated: “deploy L2 on top 5 mathematically sound factors.”
That risks changing the product under test.

If the actual engine emits a fused rating using 13 signals, the first L2 should record and test **that emitted product**, not a hand-selected clean subset.

You can add a diagnostic “core-only” strategy later.

Canonical order:

1. test actual emitted rating;
2. test factor-only/core-only ablation;
3. test pruned version after evidence.

Do not let L2 become another backfit selection layer.

---

### Misleading: “Next-Day Open is the ultimate truth-teller.”
Next-day open is fine if open data is reliable and the model run timing supports it.

But with yfinance/free daily data, next-day close can be more robust and less sensitive to open-price gaps/data oddities. The key is not open vs close; the key is **strictly after signal generation**.

Correct rule:

> fill at the first price after the signal could have been known, using a price field you trust enough to persist.

---

### Overstated: “drop unstructured text/news/political inputs.”
Maybe right, but not proven from the supplied reviews.

Drop rules should be evidence-based:

- low IC;
- low coverage;
- high staleness;
- high correlation with stronger signals;
- high implementation fragility;
- no forward contribution.

“Text/news/political are probably noise” is a prior, not a conclusion.

---

## Review D

Review D has the most problematic claims.

### Wrong: decorator self-registration plus lazy metadata.
D says use decorators but “prevent eager imports” and “only load metadata at startup.”

That is internally inconsistent.

Decorator metadata exists only after the module defining the decorator has been imported. If the metadata lives beside compute code, discovering the full registry requires importing all signal modules.

That causes exactly the serverless/cold-start problem A/B/C correctly warn about.

Only ways around this:

1. eager import all modules — bad;
2. maintain a separate list of modules to import — you are back to duplicated registry;
3. store metadata separately — which is the central manifest.

So D’s registry recommendation should be rejected.

---

### Wrong / irrelevant: Redis-caching registry metadata.
For static signal metadata in a one-repo, single-user app, Redis is worse than useless.

It adds:

- another dependency;
- invalidation complexity;
- deployment skew;
- failure mode.

Static metadata should be importable from a pure Python file and generated into TS at build time.

---

### Misread: “central tuple fails because signals still require manual import.”
The proposed string-path registry does not require manual imports at use sites. It requires one manifest row per signal. That is the correct explicitness.

The current problem is ten scattered edits. A central row is not the same failure mode.

---

### Wrong: “query `daily_prices` for existence on rebalance_date” solves point-in-time survivorship.
It does not.

A ticker having a price row on a date does not prove it was in the eligible universe as known at decision time. It also does not capture index membership, stale feeds, eligibility reason, or failed signal coverage.

You need to snapshot:

```text
run_id
ticker
in_universe
eligible
eligibility_reason
coverage
tier/composite/rank
data_asof
generated_at
```

---

### Dangerous: “backfill dead tickers via Yahoo or assume -100% return.”
Both are bad as blanket rules.

- Yahoo backfill can be restated and symbol-mapped inconsistently.
- Assuming -100% on every missing ticker is overly punitive and can create false negatives.

Better:

1. carry last valid price briefly;
2. check corporate action/manual map;
3. force exit after stale threshold;
4. apply conservative penalty if unresolved;
5. preserve the event and flag it.

---

### Overstated: Almgren-Chriss / `turnover^1.5`.
For S&P 500 names, single-user paper capital, free-data context, nonlinear impact modeling is fake precision.

Simple per-side bps plus turnover reporting is easier, more auditable, and probably more honest.

Use:

```text
cost_bps_per_side = 5 / 10 / 20 scenario grid
```

not an institutional impact model unless there is actual size/liquidity modeling.

---

### Wrong: “drop IC < 0.06.”
Hard IC cutoff is bad methodology.

A 0.043 IC signal can still help if:

- decorrelated;
- low turnover;
- stable;
- cheap to compute;
- improves tail/risk behavior;
- works in a specific horizon/regime.

Drop by **incremental contribution**, not standalone IC.

Correct pruning criterion:

```text
drop if low IC + high correlation/redundancy + poor coverage/staleness + no forward contribution
```

---

### Unsupported: “activate EWMA-ICIR immediately; dynamic weighting outperforms static fusion.”
This is asserted, not proven.

In noisy, short samples, adaptive weights can overfit and destabilize production. If activated, it must be heavily shrunk and capped.

Safe adaptive policy:

```text
effective_weight =
  80–95% static prior
  + 5–20% adaptive candidate
```

with:

- min sample;
- max per-signal move;
- max total turnover in weights;
- fallback on missing IC;
- persisted effective weights per run.

---

## 3. What all reviews missed

### A. The first deliverable should be an operational run contract, not a dashboard or schema.
Everyone talks about snapshots, but nobody fully specifies the run lifecycle.

You need a hard contract:

```text
scheduled_for_date
started_at
finished_at
data_asof
market_calendar_date
run_status: started | partial | complete | failed | corrected
code_version
registry_hash
input_data_cutoff
output_snapshot_written_at
```

And rules:

- one canonical daily run per market date;
- idempotent reruns create new run IDs, not overwrites;
- corrections are explicit correction runs;
- partial runs are not eligible for L2;
- L2 consumes only `complete` runs before cutoff.

Without this, “immutable ledger” still becomes messy.

---

### B. Nobody separated product truth from research truth sharply enough.
There are two ledgers:

1. **User-visible product ledger**  
   What the user actually saw: tier, card, rank, coverage, warnings.

2. **Research diagnostic ledger**  
   Signal z-scores, raw components, ranks, deciles, ablations.

L2 should first test the user-visible product. Research diagnostics can explain why it worked or failed.

If you only snapshot signal internals but not the emitted card/rating, you cannot answer: “Did the actual product tell me something useful?”

---

### C. Nobody specified abstention/no-trade policy.
For free data, the engine needs a first-class “do not trust this output” state.

Examples:

```text
eligible = false
reason = stale_price
reason = insufficient_signal_coverage
reason = missing_benchmark_price
reason = partial_run
reason = universe_unknown
```

Do not force every ticker into BUY/HOLD/SELL. A bad input should produce abstention, not a confident tier.

This matters more than another factor.

---

### D. Nobody addressed calibration of the displayed tier thresholds.
The system maps fused scores into BUY/OW/HOLD/UW/SELL. L2 and forward IC will be corrupted if thresholds are arbitrary.

You need to persist and evaluate:

```text
tier_threshold_version
thresholds
hysteresis policy
coverage damping policy
```

Then ask:

- Does BUY outperform OW?
- Does OW outperform HOLD?
- Does SELL underperform?
- Are tiers monotonic after costs?
- Are tier transitions useful or just churn?

The product is tiered. Therefore tier monotonicity is a core validation target.

---

### E. Nobody gave the simplest kill-switch metric.
Before building rich L2, add a daily report:

```text
coverage %
stale signal count
number of eligible names
turnover implied by top basket
BUY/SELL count
top/bottom sector concentration
missing price count
benchmark price availability
```

If those are unstable, portfolio P&L is not interpretable.

---

### F. Nobody emphasized raw input provenance enough.
Persisting outputs is necessary but insufficient for debugging.

At minimum, for each run store:

```text
price_source
price_downloaded_at
vendor_symbol
adjustment_mode
universe_source
universe_downloaded_at
feed_failure_summary
```

You do not need to store every raw bar immediately, but you need enough provenance to explain a bad run.

---

### G. Nobody called out that “single-user” changes the optimization target.
This is not a fund. You do not need institutional breadth, latency, plugin systems, or multi-strategy research infra.

You need:

1. no silent drift;
2. no lookahead;
3. no fake confidence;
4. stable user-facing decisions;
5. cheap maintainability.

That changes rankings. A dumb, auditable, long-only paper book may be more valuable than a theoretically cleaner beta-neutral rank book.

---

## 4. Re-ranked union of real recommendations  
Ranked by **leverage × confidence × ease** for this **single-user, free-data** context.

## 1. Build the immutable daily product ledger.
**Highest leverage. Highest confidence. Moderate ease.**

This beats both original proposals as the first truth-building step.

Minimum table:

```sql
research_run(
  id,
  scheduled_for_date,
  run_type,
  status,
  generated_at,
  finished_at,
  data_asof,
  code_version,
  registry_hash,
  weight_policy_id,
  tier_threshold_version
)

rating_snapshot(
  run_id,
  ticker,
  in_universe,
  eligible,
  eligibility_reason,
  composite_z,
  rank,
  tier,
  coverage,
  effective_weight_json,
  user_visible_payload_json
)
```

Rules:

- append-only;
- no overwrite;
- corrections are new runs;
- L2 only consumes complete runs;
- snapshot exactly what the user saw.

---

## 2. Add run health / abstention gates.
**Very high leverage. High confidence. Easy.**

Before portfolio simulation, make bad runs obvious.

Daily checks:

```text
eligible ticker count
coverage distribution
stale feed count
missing prices
BUY/OW/HOLD/UW/SELL counts
top sector concentration
signals failed
benchmark available
```

If a run is partial or stale-heavy, mark it non-tradable.

This prevents fake L2 from consuming garbage.

---

## 3. Implement the data-only signal registry with string import paths.
**High leverage. Very high confidence. Easy/moderate.**

Use central manifest, separated meanings:

```python
SignalMeta(
    name="rsrs",
    runtime=SignalRuntime(
        module_path="alpha_agent.signals.rsrs",
        compute_fn="compute",
        cron_group="daily",
        enabled_in_live=True,
    ),
    research=SignalResearch(
        horizon_days=20,
        active_in_ic=True,
        core_for_coverage=True,
        default_weight=0.04,
        fusion_cap=0.25,
    ),
    display=SignalDisplay(
        label_en="RSRS",
        label_zh="RSRS斜率",
    ),
)
```

Hard rules:

- registry imports no signal modules;
- signal modules do not import registry;
- lazy import only at execution site;
- invariant tests;
- import-cost test;
- derived backend lists;
- frontend TS codegen.

Reject decorator self-registration.

---

## 4. Delete obviously dead legacy paths before wiring the registry.
**High leverage. High confidence. Easy if import graph is clean.**

Especially `llm/_legacy`, if truly unused.

Do:

```text
grep/import graph
tag repo
delete
run tests
then registry migration
```

Do not preserve dead code in the new clean system.

---

## 5. Generate frontend signal metadata at build time.
**Medium/high leverage. Very high confidence. Easy.**

Produce:

```text
frontend/src/generated/signal-registry.gen.ts
```

Fail CI if stale.

Runtime registry endpoint may exist only for debug.

---

## 6. Resolve inert adaptive weights.
**High leverage. Medium confidence. Moderate ease.**

Do **not** leave “adaptive” weights computed but ignored.

Acceptable outcomes:

### Option A — research-only
Keep computing them, but label clearly:

```text
adaptive_weights_status = research_only
used_in_live = false
```

### Option B — guarded activation
Use shrinkage:

```text
effective = 0.90 * static_prior + 0.10 * adaptive
```

with:

- min sample;
- cap per-signal changes;
- nonnegative weights unless explicitly allowed;
- max turnover in weights;
- fallback on missing IC;
- persist effective vector per run.

### Option C — delete
If no owner and no trust, remove.

Best first move: **research-only or guarded 10% blend**, not full activation and not immediate deletion.

---

## 7. Build minimal L2 long-only user book on top of the ledger.
**High leverage. High confidence. Moderate.**

Canonical strategy:

```text
universe: eligible names from completed snapshot
selection: top 50 by rank, preferably BUY/OW first then fill by rank
weighting: equal weight
max position: 2%
rebalance: weekly
execution: D signal after close -> D+1 close or D+1 open if reliable
costs: 10 bps per side default, also show 5/20 bps sensitivity
benchmark: SPY adjusted return; secondary RSP if available
cash: allowed or fill-from-rank, pre-register one
```

This answers the user’s real question:

> If I mechanically followed the ratings, did I beat a simple ETF after costs?

---

## 8. Add broad rank/decile diagnostic book.
**Medium/high leverage. Medium confidence. Moderate.**

This answers the research question better than top-N.

Examples:

- top decile vs bottom decile;
- rank-weighted spread;
- beta-neutral diagnostic if you can do it simply;
- sector exposure report.

But do not let this replace the user book.

---

## 9. Persist L2 orders/fills/equity, not just recomputed curves.
**Medium/high leverage. High confidence. Moderate.**

Minimum:

```sql
l2_strategy
l2_order
l2_equity_daily
```

Then add:

```sql
l2_fill
l2_position_daily
```

when needed.

Critical rule:

> orders are generated from a prior snapshot and persisted before fill prices are consumed.

---

## 10. Add stale/delisting handling.
**Medium leverage. High confidence. Moderate/hard.**

Rules:

```text
missing 1 day: carry last price, flag stale
missing > K days: force exit or manual corporate-action resolution
unknown forced exit: apply conservative penalty
never silently drop held positions
```

This is essential before trusting multi-month L2.

---

## 11. Prune signals by incremental contribution, not raw IC.
**Medium leverage. Medium confidence. Moderate.**

Reject Review D’s hard `IC < 0.06` cutoff.

Use a table:

```text
signal
IC_5d
IC_20d
coverage
staleness
turnover contribution
correlation_to_factor
incremental rank IC
L2 ablation contribution
maintenance cost
```

Drop candidates:

```text
low IC
+ high correlation with stronger signal
+ flaky coverage
+ high maintenance
+ no forward/L2 contribution
```

Likely suspects: political/geopolitical/supply-chain/free-text signals. But prove it.

---

## 12. Freeze LLM/evolution expansion until forward truth exists.
**Medium leverage. High confidence. Easy.**

Do not necessarily delete all of it immediately. But stop adding new factor-generation complexity until:

- product ledger is stable;
- L2 has enough runs;
- current signals are pruned;
- adaptive policy is resolved.

For now:

```text
LLM proposer: frozen
sandbox: no new production dependency
evolution search: research-only
```

---

## 13. Add tier monotonicity validation.
**Medium leverage. High confidence. Easy/moderate.**

Each month report:

```text
avg forward return by tier
BUY > OW > HOLD > UW > SELL?
turnover by tier transition
coverage by tier
hit rate by tier
```

If tiers are not monotonic, the product UI is misleading even if rank IC is positive.

---

## 14. Add regime diagnostics later.
**Low/medium leverage. Medium confidence. Moderate.**

Review D’s regime testing is not wrong, but it is not first-order.

Do after:

1. ledger;
2. registry;
3. L2;
4. pruning.

Regime splits are easy to overfit with short forward samples.

---

## 15. Avoid institutional cost models for now.
**Low leverage. Medium confidence. Easy.**

Do not implement Almgren-Chriss-style impact for this context.

Use simple scenario costs:

```text
5 bps
10 bps
20 bps
```

Per side. Report turnover. That is more honest and maintainable.

---

# Final adversarial verdict

The strongest combined answer is:

1. **Build the append-only product ledger first.**
2. **Then registry consolidation using a data-only string-path manifest.**
3. **Then minimal L2 on top of real emitted snapshots.**
4. **Resolve inert adaptive weights.**
5. **Freeze expansion machinery.**
6. **Prune signals only by incremental, forward, low-drift contribution.**

Reject Review D’s decorator registry, Redis cache, hard IC cutoff, and immediate full adaptive activation. Those are the clearest misreads.

The core danger is not that the engine lacks sophistication. It has too much sophistication relative to the data. The missing layer is not more alpha machinery. It is a boring, causal, append-only truth system that records exactly what the engine believed, when it believed it, and whether a user could have acted on it.