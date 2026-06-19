# Council Chairman Verdict

## 1. Proposal Calls

| Proposal | Call | One decisive reason |
|---|---:|---|
| **Proposal 1 — Signal registry** | **GO-WITH-CHANGES** | The drift problem is real, but the registry must be a **data-only manifest with string import paths**, not decorator/self-registration or eager imports. |
| **Proposal 2 — L2 paper-trading** | **GO-WITH-CHANGES** | IC is not enough, but L2 is only honest if it starts from an **immutable point-in-time product ledger** and uses causal execution, costs, and stale-feed handling. |

Bluntly: **both proposals are right, but both must be made boring.** No plugin system. No brokerage cosplay. No dashboard theater.

---

# 2. Minimal Correct Design

## Proposal 1 — Minimal correct signal registry

Must-haves:

1. **Central, data-only manifest**
   - Pure Python/dataclass file.
   - No pandas, yfinance, sklearn, signal modules, fusion modules, cron modules, or API imports.
   - Signal implementation modules must not import the registry.

2. **String import paths only**

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
    data_deps=("daily_prices.high", "daily_prices.low"),
)
```

3. **Separate meanings**
   - Do not use one vague `tier`.
   - Use explicit fields:
     - `cron_group`
     - `core_for_coverage`
     - `research_stage`
     - `display_group`
     - `rating_tier` only for BUY/OW/HOLD/UW/SELL output, not cron grouping.

4. **Derived backend views**
   - `DEFAULT_WEIGHTS`
   - signal horizons
   - active IC set
   - health signal list
   - cron module lists
   - fusion core set  
   all generated from the manifest.

5. **Frontend build-time codegen**
   - Generate `frontend/src/generated/signal-registry.gen.ts`.
   - Fail CI if stale.
   - Runtime `/api/_signal_registry` may exist only for debugging.

6. **Tests**
   - Migration snapshot tests: derived values equal current hardcoded values.
   - Permanent invariant tests: unique names, nonnegative weights, active signals have horizons, enabled signals have module paths.
   - Lazy-import regression test: importing registry must not import `yfinance`, pandas, or signal modules.
   - Frontend codegen freshness test.

7. **Persist with runs**
   - Each run should store:
     - `registry_hash`
     - `weight_policy_id`
     - `effective_weight_vector`
     - `active_signal_set`
     - `tier_threshold_version`

---

## Proposal 2 — Minimal correct L2

The first deliverable is **not a portfolio dashboard**. It is the **append-only product ledger**.

### Required run contract

```sql
research_run(
  id,
  scheduled_for_date,
  run_type,
  status, -- started | partial | complete | failed | corrected
  started_at,
  finished_at,
  data_asof,
  input_data_cutoff,
  code_version,
  registry_hash,
  weight_policy_id,
  tier_threshold_version
)
```

Rules:

- One canonical daily run per market date.
- No overwrites.
- Corrections create new run IDs.
- Partial runs are not tradable.
- L2 consumes only `complete` runs before the execution cutoff.

### Required product snapshot

```sql
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
  user_visible_payload_json,
  price_source,
  price_downloaded_at,
  adjustment_mode,
  feed_status
)
```

This must capture **what the user actually saw**, not what the model would recompute later.

### Minimal L2 strategy

Canonical user-facing book:

```text
Universe: eligible names from completed snapshot
Selection: top 50 by rank, BUY/OW preferred, then fill by rank
Weighting: equal weight
Max position: 2%
Rebalance: weekly
Execution: signal after close D -> fill D+1 close by default
Costs: 10 bps per side default; also report 5/20 bps sensitivity
Benchmark: SPY adjusted return; secondary RSP if available
Cash: pre-register either hold cash or fill from next ranks
```

Why D+1 close: with free daily/yfinance-style data, next-day close is usually less self-deceiving than next-day open unless open-price reliability is explicitly validated.

### Required L2 persistence

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

> Orders must be generated from a prior immutable snapshot and persisted before execution prices are consumed.

### Required honesty controls

- Report gross and net returns.
- Report turnover.
- Report stale-price count.
- Report missing-price count.
- Report BUY/OW/HOLD/UW/SELL counts.
- Report sector concentration.
- Report beta to SPY.
- Show confidence bands; do not let six months of noise look like proof.

### Stale/dead-feed handling

Held positions cannot silently disappear.

Rules:

```text
Missing 1 day: carry last valid price, flag stale.
Missing > K days: force exit or require corporate-action resolution.
Unknown forced exit: apply conservative penalty.
Ticker changes: explicit symbol map or manual correction run.
Never drop a held position without an exit event.
```

---

# 3. Prioritized Roadmap

Ranked for this **single-user, free-data engine** by leverage × confidence × ease.

| # | Problem | Concrete fix | ICE read | Consensus |
|---:|---|---|---|---|
| **1** | The engine has no causal memory of what it believed when. | Build the append-only `research_run` + `rating_snapshot` product ledger. Store user-visible output, eligibility, coverage, registry hash, weight policy, thresholds, and data provenance. | **I 5 / C 5 / E 3** | **Very strong** |
| **2** | Bad runs can be accidentally treated as tradable truth. | Add run health and abstention gates: eligible count, stale feeds, missing prices, failed signals, benchmark availability, BUY/SELL counts, sector concentration. Mark bad runs non-tradable. | **I 5 / C 5 / E 4** | **Very strong** |
| **3** | Signal metadata is drifting across backend, cron, backtest, health, CLI, and frontend. | Implement the data-only string-path registry; derive all backend lists; generate frontend TS; add lazy-import and invariant tests. | **I 4 / C 5 / E 3** | **Near-unanimous** |
| **4** | Dead/legacy discovery code risks being resurrected during refactor. | Before registry wiring, prove unused via import graph, tag repo, delete `llm/_legacy`, and freeze new LLM/evolution/sandbox expansion. | **I 4 / C 5 / E 5** | **Strong** |
| **5** | “Adaptive weights” are computed but ignored, which creates false capability. | Force a decision: research-only with explicit labeling, guarded 10% shrink-to-prior activation, or delete. Do not leave inert. | **I 4 / C 4 / E 3** | **Strong on problem, split on remedy** |
| **6** | IC does not prove investable user value. | Build minimal L2 long-only user book on top of the ledger: weekly, top 50, equal weight, D+1 close, 10 bps/side, SPY/RSP benchmark, gross/net/turnover. | **I 4 / C 5 / E 3** | **Strong** |
| **7** | Top-N user book may miss broad ranking information. | Add research diagnostic: decile spread or broad rank-weighted book; beta/sector exposure report; label it diagnostic, not user portfolio. | **I 3 / C 4 / E 3** | **Moderate/strong** |
| **8** | Weak/noisy signals may dilute the fused rating. | Prune by incremental contribution, not raw IC: low IC + high correlation + poor coverage/staleness + no forward/L2 contribution. Do not hard-drop RSRS by IC alone. | **I 4 / C 4 / E 3** | **Strong on method, split on targets** |
| **9** | Product tiers may be visually authoritative but statistically non-monotonic. | Add monthly tier validation: BUY > OW > HOLD > UW > SELL forward return, turnover by tier transition, hit rate by tier, coverage by tier. | **I 3 / C 5 / E 4** | **Strong** |

---

# 4. Single Highest-Leverage Move

**Start writing an immutable daily product ledger now.**

That one move enables honest L2, honest forward IC, drift detection, adaptive-weight validation, tier monotonicity checks, and forensic debugging.

Without it, every other validation layer can quietly recompute the past and fool you.

---

# 5. Split Findings and Tie-Breaks

## Split 1 — Central manifest vs decorator self-registration

**Tie-break: central data-only manifest wins.**

Decorators require importing signal modules to populate the registry. That breaks serverless cold-start hygiene and makes discovery depend on import side effects. For this repo, explicit manifest rows are better than plugin cleverness.

Rejected:

```python
@register_signal(...)
def compute(...):
    ...
```

Accepted:

```python
SignalMeta(
    name="rsrs",
    module_path="alpha_agent.signals.rsrs",
    compute_fn="compute",
)
```

---

## Split 2 — Top-N long-only vs broad rank-weighted L2

**Tie-break: both, but different jobs.**

- **Primary product test:** long-only top 50 vs SPY/RSP.  
  This answers: “Should the single user trust the emitted ratings?”

- **Primary research diagnostic:** decile spread or broad rank-weighted book.  
  This answers: “Is there cross-sectional ranking alpha?”

Do not make the beta-hedged institutional book the only truth layer for a single-user product.

---

## Split 3 — Next-day open vs next-day close

**Tie-break: default to D+1 close.**

Next-day open is acceptable only if open-price quality is validated. With free daily data, D+1 close is less fragile and still causally honest.

Rule:

> Signal after close D; fill at the first later price you trust. Default: D+1 close.

---

## Split 4 — Adaptive weights: activate, delete, or keep inert

**Tie-break: inert is forbidden; full activation is also forbidden.**

Acceptable options:

1. **Research-only**, explicitly labeled not live.
2. **Guarded activation**, e.g.:

```text
effective_weight = 0.90 * static_prior + 0.10 * adaptive_candidate
```

with min sample, caps, nonnegative constraints, fallback rules, and persisted effective weights.

3. **Delete**, if no owner or no trust.

Do **not** flip EWMA-ICIR fully live on noisy free-data IC.

---

## Split 5 — Hard IC cutoff / drop RSRS

**Tie-break: no hard IC cutoff.**

Dropping `IC < 0.06` is bad methodology. A low-IC signal can help if it is decorrelated, stable, cheap, and low-turnover.

Prune only if:

```text
low IC
+ redundant correlation
+ poor coverage/staleness
+ high maintenance
+ no forward contribution
```

RSRS stays unless its decorrelation/incremental-contribution thesis fails.

---

## Split 6 — Delete LLM/evolution/sandbox now vs freeze

**Tie-break: delete obvious legacy; freeze expansion.**

- Delete `llm/_legacy` if import graph proves it is unused.
- Freeze new LLM factor/evolution/sandbox expansion.
- Do not spend more engineering effort discovering exotic weak signals until the ledger and L2 prove the current product has forward value.

---

# Final Direction

**Do not build more alpha machinery right now.**

The correct direction is:

1. **Append-only product ledger.**
2. **Run health and abstention gates.**
3. **Data-only signal registry with frontend codegen.**
4. **Delete dead legacy and freeze discovery expansion.**
5. **Resolve adaptive weights.**
6. **Minimal causal L2 on emitted snapshots.**
7. **Then prune signals by incremental forward contribution.**

The engine does not currently need more sophistication.  
It needs **causal memory, fewer silent drift paths, and fewer ways to lie to itself.**