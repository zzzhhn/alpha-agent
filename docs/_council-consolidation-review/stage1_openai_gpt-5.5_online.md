## Executive read

You have **two different problems**:

1. **Engineering truth problem:** signal definitions, active sets, weights, horizons, UI labels, cron tiers, and backtest lists are drifting. Proposal 1 addresses this directly. It is a high-leverage hygiene fix.
2. **Research truth problem:** IC tells you whether ranks have weak cross-sectional information, but not whether the actual end-to-end product survives timing, turnover, missing data, tier thresholds, stale feeds, and costs. Proposal 2 addresses this directly. It is the more important trust-building step.

The blunt version: **the registry is necessary engineering hygiene; L2 is necessary epistemic hygiene.** Do both, but keep both smaller than proposed. Do not use either as an excuse to add more signal/evolution machinery.

---

# Proposal 1 — Signal registry consolidation

## Is the proposal sound?

Yes. The diagnosis is correct: the fragmentation is **registration/configuration sprawl**, not duplication of factor logic.

You should consolidate the signal metadata.

The strongest evidence is that adding RSRS required edits across:

- fusion weights
- signal horizons
- fusion core set
- backtest active set
- CLI card generation
- cron modules
- cron tiers
- health route signal list
- frontend weight override mirror
- frontend horizon mirror
- frontend label mirror

That is exactly the class of problem a registry solves.

But the right pattern is not “one object imports all signal modules.” The right pattern is:

> **A data-only signal manifest containing stable metadata and import paths as strings, from which backend and frontend artifacts are generated.**

The registry should not execute signal code at import time. It should not import `yfinance`, EDGAR clients, news clients, factor engines, or cron code.

---

## Strongest objection

The strongest objection is that a central registry can become a **god config** that mixes unlike concerns:

- research identity
- runtime orchestration
- UI labels
- default weights
- adaptive live weights
- backtest active set
- cron frequency
- coverage damping behavior
- signal caps
- data dependencies
- execution module import paths

If you put everything in one flat `SignalMeta`, the registry becomes the place where every subsystem negotiates its own meanings. Then you get a cleaner-looking version of the same coupling.

The failure mode is subtle: all lists derive from the registry, but the registry’s fields become overloaded.

Example:

```python
tier="fast"
```

Could mean:

- intraday cron tier?
- UI grouping?
- freshness expectation?
- research maturity?
- fusion priority?
- latency budget?

Those must not be the same field unless they truly mean the same thing.

---

## Better / minimal / less-self-deceiving version

Use a **typed, data-only manifest** with separated concerns.

Something like:

```python
# alpha_agent/signals/registry.py

from dataclasses import dataclass
from typing import Literal

SignalName = Literal[
    "factor",
    "technicals",
    "rsrs",
    "analyst",
    "earnings",
    "news",
    "insider",
    "options",
    "premarket",
    "macro",
    "calendar",
    "political_impact",
    "geopolitical_impact",
    "supply_chain",
]

@dataclass(frozen=True)
class SignalRuntime:
    module_path: str              # string only; no eager import
    compute_fn: str               # usually "compute"
    cron_group: Literal["fast_intraday", "daily", "slow", "manual"]
    enabled_in_live: bool

@dataclass(frozen=True)
class SignalResearch:
    horizon_days: int
    active_in_ic: bool
    core_for_coverage: bool
    default_weight: float
    fusion_cap: float | None
    min_coverage_required: bool

@dataclass(frozen=True)
class SignalDisplay:
    label_en: str
    label_zh: str
    description_en: str | None = None

@dataclass(frozen=True)
class SignalMeta:
    name: SignalName
    runtime: SignalRuntime
    research: SignalResearch
    display: SignalDisplay
    data_deps: tuple[str, ...]
```

Then:

```python
SIGNALS: tuple[SignalMeta, ...] = (
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
            min_coverage_required=False,
        ),
        display=SignalDisplay(
            label_en="RSRS",
            label_zh="RSRS斜率",
        ),
        data_deps=("daily_prices.high", "daily_prices.low"),
    ),
)
```

Then derive:

```python
DEFAULT_WEIGHTS = {
    s.name: s.research.default_weight
    for s in SIGNALS
    if s.runtime.enabled_in_live
}

SIGNAL_HORIZONS = {
    s.name: s.research.horizon_days
    for s in SIGNALS
    if s.research.active_in_ic
}

_CORE_SIGNALS = tuple(
    s.name for s in SIGNALS
    if s.research.core_for_coverage and s.runtime.enabled_in_live
)

_ACTIVE_SIGNALS = tuple(
    s.name for s in SIGNALS
    if s.research.active_in_ic
)

_FAST_INTRADAY_MODULES = {
    s.name: f"{s.runtime.module_path}:{s.runtime.compute_fn}"
    for s in SIGNALS
    if s.runtime.enabled_in_live and s.runtime.cron_group == "fast_intraday"
}

HEALTH_SIGNAL_NAMES = tuple(
    s.name for s in SIGNALS
    if s.runtime.enabled_in_live
)
```

### Important distinction

Do **not** treat `default_weight` as the only possible live weight.

You want:

1. **Registry default weight**: static fallback / initial prior.
2. **WeightPolicy**: live hand-set policy or adaptive policy.
3. **DB adaptive weights**: learned candidate weights.
4. **Effective fusion weights**: actual weights used for a run, persisted with the run.

The registry should define the default prior, not hide the current policy.

---

## Central tuple vs per-signal decorator self-registration

For this system, prefer the central data manifest.

### Why not decorator self-registration?

A decorator registry usually implies this:

```python
@register_signal(...)
def compute(...):
    ...
```

Then to discover registered signals you must import all signal modules. That causes:

- eager imports in serverless cold starts
- hidden import-time side effects
- accidental network client initialization
- circular imports between signal modules and orchestration
- nondeterministic failure if one signal import breaks
- harder codegen because frontend generation now depends on importing backend code
- painful testing because “registry state” mutates at import time

Self-registration is attractive when you have many plugins owned by many teams. You do not. You have one repo and one user. A central manifest is simpler and more auditable.

### Best compromise

Keep metadata centralized, but colocate signal-specific docs/tests with the signal module.

Example structure:

```text
alpha_agent/signals/
  registry.py
  rsrs.py
  rsrs.md
  tests/test_rsrs.py
```

The registry says:

```python
module_path="alpha_agent.signals.rsrs"
```

The implementation stays separate.

---

## Trap: circular imports

Preempt this with one rule:

> Signal implementation modules must not import the registry.

Bad:

```python
# signals/rsrs.py
from alpha_agent.signals.registry import get_meta
```

Good:

```python
# signals/rsrs.py
SIGNAL_NAME = "rsrs"

def compute(...):
    ...
```

The orchestrator imports registry. Signal modules are leaf modules.

Also avoid this:

```python
# registry.py
from alpha_agent.signals import rsrs
```

Use strings instead:

```python
module_path="alpha_agent.signals.rsrs"
compute_fn="compute"
```

Then lazy-load only in the runner:

```python
from importlib import import_module

def load_signal(meta: SignalMeta):
    mod = import_module(meta.runtime.module_path)
    return getattr(mod, meta.runtime.compute_fn)
```

---

## Trap: import-time cost in cron

The cron must not do this:

```python
from alpha_agent.signals.registry import SIGNALS
for signal in SIGNALS:
    import_module(signal.runtime.module_path)
```

That recreates the eager-import problem.

It should filter first, import later:

```python
metas = [
    s for s in SIGNALS
    if s.runtime.enabled_in_live
    and s.runtime.cron_group == "fast_intraday"
]

for meta in metas:
    fn = load_signal(meta)
    run_signal(fn)
```

Also log import duration per signal. If one signal import suddenly takes 2 seconds because it initializes a model, you want to know.

---

## Trap: deriving `DEFAULT_WEIGHTS`, `_CORE_SIGNALS`, `_TIERS` from one object

This is okay if the meanings are separated.

Do not use one vague field like:

```python
tier="core"
```

Use explicit fields:

```python
core_for_coverage=True
cron_group="fast_intraday"
ui_group="market_structure"
research_stage="live"
```

Otherwise you will accidentally couple unrelated policies.

### Better field naming

Avoid `_TIERS` unless it is clear what it means.

Prefer:

```python
cron_group
ui_group
rating_tier
research_stage
```

If `_TIERS` means cron scheduling, name it `cron_group`.

If it means UI display grouping, name it `display_group`.

If it means signal maturity, name it `research_stage`.

---

## Frontend codegen vs runtime fetch

Use **codegen**, not runtime fetch, for the core frontend mirrors.

The frontend metadata is small, slow-changing, and should be versioned with the app. A runtime fetch adds:

- startup dependency on backend health
- loading states for static labels
- frontend/backend version skew during deployments
- extra failure mode for no real benefit

Generate:

```text
frontend/src/generated/signal-registry.gen.ts
```

from the backend registry, just like OpenAPI types.

Example generated shape:

```ts
export const SIGNAL_REGISTRY = [
  {
    name: "rsrs",
    labelEn: "RSRS",
    labelZh: "RSRS斜率",
    horizonDays: 20,
    defaultWeight: 0.04,
    coreForCoverage: true,
    cronGroup: "daily",
  },
] as const;

export type SignalName = typeof SIGNAL_REGISTRY[number]["name"];
```

Add CI:

```bash
python scripts/generate_signal_registry_ts.py
git diff --exit-code frontend/src/generated/signal-registry.gen.ts
```

Keep `/api/_signal_registry` too, but as an introspection/debug endpoint, not the normal UI dependency.

---

## Snapshot tests

Your proposed snapshot test is good but incomplete.

You need three classes of tests.

### 1. Zero-behavior-change snapshot

Assert current derived outputs equal current hardcoded outputs during migration.

```python
def test_default_weights_match_legacy_snapshot():
    assert derive_default_weights(SIGNALS) == LEGACY_DEFAULT_WEIGHTS
```

This is a migration test. Delete or replace it after migration.

### 2. Registry consistency invariants

These stay forever.

Examples:

```python
def test_signal_names_unique():
    names = [s.name for s in SIGNALS]
    assert len(names) == len(set(names))

def test_weights_nonnegative():
    for s in SIGNALS:
        assert s.research.default_weight >= 0

def test_enabled_live_signals_have_module_paths():
    for s in SIGNALS:
        if s.runtime.enabled_in_live:
            assert s.runtime.module_path
            assert s.runtime.compute_fn

def test_active_ic_signals_have_horizon():
    for s in SIGNALS:
        if s.research.active_in_ic:
            assert s.research.horizon_days > 0

def test_frontend_codegen_current():
    # regenerate and compare checked-in generated file
    ...
```

### 3. Lazy import tests

One test should assert that importing the registry does not import signal modules.

```python
def test_registry_import_is_data_only():
    import sys
    import alpha_agent.signals.registry
    assert "alpha_agent.signals.rsrs" not in sys.modules
    assert "yfinance" not in sys.modules
```

This catches the most common regression.

---

## Are you under-valuing dead-code deletion?

Yes. Dead-code deletion is higher value than it looks.

The most dangerous systems are not the ones with too little logic. They are the ones with multiple plausible old paths. In a single-user research engine, stale paths create false confidence:

- old cron path still writes partial signal rows
- old LLM/evolution code imports an older factor grammar
- legacy card builder displays deprecated signal names
- old health route says a signal is live when fusion no longer uses it
- frontend mirror contains labels for dead signals

Delete `llm/_legacy` if:

1. import graph confirms no production path uses it;
2. tests cover current factor proposer path;
3. old artifacts are archived or tagged;
4. deletion includes migration notes.

Do not leave it “just in case.” Tag the repo before deletion.

---

## Are you over-engineering the registry?

The registry itself is not over-engineering if it remains data-only.

Over-engineering would be:

- plugin discovery
- decorators
- runtime database registry for static signal metadata
- user-editable registry UI
- dynamically-loaded frontend labels
- registry-driven arbitrary DAG execution
- merging factor engine, evolution, fusion, and backtest into one mega-framework

Do not do those.

Build the dumb manifest.

---

## Concrete implementation plan

### Phase 1 — Add data-only registry

- Add `signals/registry.py`.
- Use string import paths.
- Add derivation helpers.
- Add invariant tests.
- Do not delete old lists yet.

### Phase 2 — Replace backend lists one by one

Replace:

- `fusion/weights.DEFAULT_WEIGHTS`
- `signals/horizons`
- `fusion/policy._CORE_SIGNALS`
- `backtest/ic_engine._ACTIVE_SIGNALS`
- `cli/build_card._SIGNAL_NAMES`
- fixture map
- `api/cron/fast_intraday._ALL_MODULES`
- `api/cron/fast_intraday._TIERS`
- `api/routes/health._SIGNAL_NAMES`

Each replacement should be a one-line derivation or import from a derivation helper.

### Phase 3 — Generate frontend registry

Generate:

- `weights-override.ts`
- `signal-horizons.ts`
- `signal-labels.ts`

or better, replace the three with one generated:

```text
signal-registry.gen.ts
```

### Phase 4 — Delete legacy and mirrors

Delete old hardcoded lists after one deploy cycle.

### Phase 5 — Persist effective registry version in runs

Every signal/fusion run should record:

```text
registry_schema_version
registry_hash
weight_policy_id
effective_weight_vector
active_signal_set
```

This matters later when L2 asks, “what exactly did we believe on that day?”

---

# Proposal 2 — L2 forward paper-trading

## Is L2 the right next verification step?

Yes, with a caveat.

It is the right next verification step if you build it as a **minimal forward audit harness**, not as a fake brokerage system.

IC answers:

> Did the score correlate with future cross-sectional returns?

L2 answers:

> Did the actual product’s daily calls, as emitted at the time, produce investable net returns after timing, missing data, coverage, turnover, and costs?

Those are different questions.

For a user who wants to trust the output, L2 is more persuasive than another IC table.

---

## Strongest objection

The strongest objection is that L2 may become a **performance theater layer** over weak signals.

A paper portfolio can look real while still being self-deceptive because it often smuggles in:

- survivorship bias
- same-close execution
- retroactively fixed signal rows
- stale prices
- missing delistings
- ignored costs
- untracked turnover
- benchmark mismatch
- unmodeled borrow costs for shorts
- multiple portfolio variants until one looks good

If you build L2 poorly, it will increase confidence without increasing truth.

---

## Minimal correct design

Build the smallest L2 that preserves causality.

The core object is not “portfolio.” The core object is an **immutable daily decision snapshot**.

### Required tables

#### `research_run`

One row per engine run.

```sql
create table research_run (
    id uuid primary key,
    run_type text not null, -- daily_close, intraday, manual
    generated_at timestamptz not null,
    data_asof timestamptz not null,
    registry_hash text not null,
    weight_policy_id text not null,
    code_version text not null,
    notes text
);
```

#### `signal_snapshot`

Per ticker, per signal, per run.

```sql
create table signal_snapshot (
    run_id uuid not null references research_run(id),
    ticker text not null,
    signal_name text not null,
    z numeric,
    confidence numeric,
    coverage_flag boolean not null default true,
    source_updated_at timestamptz,
    primary key (run_id, ticker, signal_name)
);
```

#### `rating_snapshot`

Final composite output as seen by the user.

```sql
create table rating_snapshot (
    run_id uuid not null references research_run(id),
    ticker text not null,
    composite_z numeric,
    tier text not null, -- BUY, OW, HOLD, UW, SELL
    effective_weight_json jsonb not null,
    coverage numeric not null,
    rank integer,
    eligible boolean not null,
    in_universe boolean not null,
    primary key (run_id, ticker)
);
```

#### `l2_strategy`

Defines the paper strategy, not the engine.

```sql
create table l2_strategy (
    id text primary key,
    description text not null,
    rebalance_frequency text not null, -- weekly, monthly
    execution_lag text not null,       -- next_open, next_close
    long_count integer not null,
    short_count integer not null default 0,
    weighting text not null,           -- equal, rank_scaled
    max_position_weight numeric not null,
    cost_bps_per_side numeric not null,
    slippage_bps_per_side numeric not null,
    benchmark text not null,
    created_at timestamptz not null
);
```

#### `l2_order`

Orders generated from a past snapshot.

```sql
create table l2_order (
    strategy_id text not null references l2_strategy(id),
    rebalance_date date not null,
    run_id uuid not null references research_run(id),
    ticker text not null,
    target_weight numeric not null,
    generated_at timestamptz not null,
    execution_date date not null,
    execution_rule text not null,
    primary key (strategy_id, rebalance_date, ticker)
);
```

#### `l2_fill`

Synthetic fills using prices available after execution date.

```sql
create table l2_fill (
    strategy_id text not null,
    execution_date date not null,
    ticker text not null,
    target_weight numeric not null,
    fill_price numeric,
    fill_price_type text, -- open, close, adjusted_close_proxy
    cost_bps numeric not null,
    filled boolean not null,
    failure_reason text,
    primary key (strategy_id, execution_date, ticker)
);
```

#### `l2_position_daily`

Daily marked positions.

```sql
create table l2_position_daily (
    strategy_id text not null,
    date date not null,
    ticker text not null,
    shares numeric not null,
    weight numeric,
    price numeric,
    market_value numeric,
    stale_price boolean not null default false,
    primary key (strategy_id, date, ticker)
);
```

#### `l2_equity_daily`

Portfolio-level equity curve.

```sql
create table l2_equity_daily (
    strategy_id text not null,
    date date not null,
    equity numeric not null,
    gross_exposure numeric not null,
    net_exposure numeric not null,
    turnover numeric,
    daily_return numeric,
    benchmark_return numeric,
    excess_return numeric,
    primary key (strategy_id, date)
);
```

---

## Minimal honest strategy

Start with one canonical strategy. Do not create ten variants.

### L2-A: Long-only top basket

Purpose: answer whether the ratings are useful to a normal user.

- Universe: tickers eligible in the daily snapshot at the time.
- Selection: top `N` by composite rank among BUY/OW, or top `N` regardless of tier if fewer BUY/OW names exist.
- `N`: 50 or 75.
- Weighting: equal weight.
- Max position: 2%.
- Rebalance: weekly.
- Execution: next trading day close, or next trading day open if open prices are reliable.
- Benchmark: SPY total-return proxy if available; otherwise adjusted SPY close. Also compare to RSP/equal-weight S&P proxy if available.
- Costs: at least 5 bps per side; preferably 10 bps per side for conservatism.
- Dividends/splits: use adjusted prices for return calculations.
- Cash: allowed.
- Shorts: no.

Why this is the right first test:

- Most aligned with user behavior.
- Avoids borrow costs.
- Avoids hard-to-model short squeezes.
- Reduces idiosyncratic noise.
- Lets you see whether OW/BUY calls beat SPY/RSP.

### L2-B: Diagnostic long-short basket

Build only after L2-A works.

- Long top 75.
- Short bottom 75.
- Equal dollar long/short.
- Gross exposure: 100% or 200%, but report both clearly.
- Costs: 10 to 20 bps per side.
- Borrow cost: crude fixed annual short borrow penalty, e.g. 2% to 5% annualized, unless unavailable names are excluded.
- Benchmark: zero, plus SPY beta-adjusted residual.
- Purpose: measure pure cross-sectional ranking, not user-investable performance.

Do not lead with long-short if the actual user will not short.

---

## Point-in-time picks only

This is non-negotiable.

The L2 portfolio must consume only rows that existed before execution.

Bad:

```python
scores = recompute_scores(today)
portfolio = top_n(scores)
```

Good:

```python
run = latest_research_run_before(rebalance_cutoff)
ratings = rating_snapshot[run.id]
portfolio = top_n(ratings)
```

Also persist the generated orders before you ingest or use the execution price.

This matters because otherwise the L2 code can accidentally see restated signals, fixed prices, new universe membership, or corrected fundamentals.

---

## Execution timing

You need explicit timing rules.

Example:

- Engine run after market close on Monday using data as of Monday close.
- Orders generated Monday night.
- Fill at Tuesday close.
- Returns begin Tuesday close to Wednesday close.

This is conservative and easy with daily data.

Avoid “same close” execution unless you can prove the signal was produced before that close and the input data did not include that close.

Given your stack uses yfinance and daily data, use:

> **signal on D after close, fill on D+1 close.**

That is slower but much less self-deceiving.

---

## Costs

Use simple but punitive costs.

For S&P 500 names, small capital, no intraday execution model:

- Long-only: 5 to 10 bps per side.
- Long-short: 10 to 20 bps per side plus borrow penalty.
- Forced stale/delisting exit: additional penalty.

Store costs as a strategy parameter, not hardcoded.

Report returns:

1. gross of costs
2. net of trading costs
3. net of trading costs plus short borrow penalty, if applicable

If gross works and net fails, the signal is probably too high-turnover or too weak.

---

## Rebalance cadence

Given your IC horizons are 5d and 20d and signal ICs are weak, daily rebalance is probably self-deception.

Start with:

- weekly rebalance for the canonical portfolio;
- optional monthly rebalance for robustness;
- no daily strategy except diagnostic.

Why?

- daily rebalancing amplifies noise;
- yfinance daily prices are not reliable enough for precise execution simulation;
- costs will eat small rank edges;
- many of your signals are slow-moving.

Use the signal’s intended horizon. If RSRS validated at 20d, do not force it into a daily churn machine.

---

## Position sizing

Use equal weight first.

Do not use confidence-weighting initially. Your confidence is isotonic-calibrated 5d directional hit-rate and structurally around 50%. It is not a reliable sizing variable.

Do not use raw composite magnitude aggressively. Composite z is a fused score, not a calibrated expected return.

Canonical sizing:

```python
target_weight = min(1 / N, max_position_weight)
```

If fewer than `N` eligible names pass the filter, either:

- hold cash, or
- fill from next ranks.

Choose one and lock it in.

For a trustable test, I would fill from next ranks. Otherwise the strategy may become a market-timing strategy accidentally.

---

## Survivorship

For forward L2, survivorship is less severe if you only use the universe recorded at the time.

You do not need historical S&P 500 membership to run L2 going forward. You need:

```text
universe_asof
eligible_at_decision_time
```

But you must not reconstruct yesterday’s universe from today’s S&P 500 list.

Every run should snapshot:

```sql
ticker
in_sp500_snapshot
eligible
eligibility_reason
```

If a ticker later leaves the index, you continue marking until the position exits by the strategy rules or corporate action handling.

---

## Dead-feed / delisting handling

This is one of the biggest ways paper portfolios lie.

Rules:

1. If a held ticker has no new price, mark it stale.
2. If stale for one day, carry last price but flag it.
3. If stale for more than `K` trading days, force an exit with a penalty unless there is a verified corporate action.
4. If yfinance changes ticker symbols, map the corporate action manually or via a maintained symbol map.
5. If delisted/acquired, use available final adjusted price if known; otherwise use conservative exit.

For S&P 500 this will not happen constantly, but when it happens, it matters.

Do not silently drop dead tickers from the portfolio. That creates upward bias.

---

## Benchmark choice

Use multiple benchmarks because each answers a different question.

### Primary benchmark

For long-only:

- SPY adjusted return.

This answers:

> Did the user beat a default market ETF?

### Secondary benchmark

- RSP or equal-weight S&P proxy.

This answers:

> Did the engine add stock-selection value beyond equal-weighting large caps?

### Diagnostic benchmark

- Sector-neutral equal-weight benchmark if you can build it.

This answers:

> Is the engine just overweighting tech, beta, momentum, or mega-cap?

At minimum, report beta to SPY and sector weights over time.

A long-only portfolio beating SPY because it ran 1.25 beta in a bull market is not alpha.

---

## Classic ways a paper portfolio lies, and preemptions

### 1. Same-close lookahead

**Lie:** Signal uses close D and fills at close D.

**Preempt:** Fill at D+1 close.

---

### 2. Recomputed historical picks

**Lie:** Backfilled signal code generates “what we would have picked.”

**Preempt:** Use immutable `rating_snapshot` rows generated in real time only.

---

### 3. Mutable ratings

**Lie:** Yesterday’s rating row gets overwritten when a bug is fixed.

**Preempt:** Append-only snapshots. No updates except explicit correction rows.

---

### 4. Missing failed feeds

**Lie:** If a signal/feed fails, the backtest recomputes later after data arrives.

**Preempt:** Store feed status and signal coverage at decision time.

---

### 5. Universe drift

**Lie:** Use today’s S&P 500 for historical forward days.

**Preempt:** Persist universe membership per run.

---

### 6. Delisting bias

**Lie:** Dead tickers disappear.

**Preempt:** Held positions remain until explicit exit.

---

### 7. Ignored transaction costs

**Lie:** Gross returns look good, net returns vanish.

**Preempt:** Apply per-side costs and report turnover.

---

### 8. Excessive variant search

**Lie:** Try top 10, 25, 50, 100; daily, weekly, monthly; long-only, long-short; then pick the winner.

**Preempt:** Pre-register one canonical L2 strategy. Treat others as diagnostics.

---

### 9. Benchmark mismatch

**Lie:** Compare a high-beta concentrated basket to SPY.

**Preempt:** Report beta, drawdown, sector weights, and RSP comparison.

---

### 10. Hidden manual intervention

**Lie:** User ignores bad picks but paper portfolio assumes mechanical obedience.

**Preempt:** Separate “engine portfolio” from “user discretionary portfolio.” L2 should be mechanical.

---

### 11. Confidence misuse

**Lie:** Size positions by 50.8% calibrated hit-rate.

**Preempt:** Do not