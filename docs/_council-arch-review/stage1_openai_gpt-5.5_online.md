## 1) Most important flaws

### 1. **The live rating policy is not the researched policy**
**Layer / mechanism:** `combine.py` consumers in `fast_intraday` and `slow_daily`; `DEFAULT_WEIGHTS`; inert `signal_weight_current`.

The central architectural flaw is not merely that adaptive weights are disconnected. It is that the system has **two competing truths**:

- Research truth: `ic_engine` says factor, technicals, and news have recently negative 5d rank IC.
- Production truth: live fusion still gives factor 0.30, technicals 0.20, news 0.10 via `DEFAULT_WEIGHTS`.

That means the visible product is not the output of the validation machinery. The validation machinery is effectively an expensive dashboard, not a control loop.

#### Why it matters concretely

This costs edge directly.

Current live weights are materially long the signals with the worst observed 5d IC:

| Signal | Static live weight | Observed 5d IC direction |
|---|---:|---|
| factor | 0.30 | negative / near-zero |
| technicals | 0.20 | clearly negative |
| news | 0.10 | negative |
| analyst | 0.10 | positive |

So the live composite is likely **anti-aligned** with the empirical 5d objective. If the observed ICs are even directionally representative, the engine is systematically elevating names that the backtest says should be penalized.

There is also a hidden governance problem: `signal_weight_current` currently says factor/news/technicals should be hard-dropped, but the UI cards still imply those signals matter according to static defaults. A user looking at methodology or factors could reasonably believe the system is adaptive when it is not.

The second concrete break is survivorship through `combine` renormalization. If a high-weight signal fails or is unavailable, its weight is silently redistributed across survivors. Example: if factor drops for off-panel names, the remaining noisy live signals become mechanically more important. Missingness becomes an implicit alpha model.

That is dangerous because missingness is not random:

- off-panel names lose factor,
- BYOK news may be absent,
- options chains fail more for less liquid names,
- yfinance transient failures hit shards unpredictably,
- supply_chain exists for only 10 hand-scored names.

The current fusion logic treats “not observed” as “do not penalize; redistribute conviction elsewhere.” That can create unstable rankings and biased treatment of names with worse data coverage.

#### Concrete optimization

Introduce an explicit **production weight policy layer** and make all live composites consume it.

Implementation-level shape:

```python
# alpha_agent/weights/policy.py

@dataclass
class WeightPolicy:
    policy_id: str
    horizon: str              # "5d", "20d", "60d", "intraday"
    mode: str                 # "static", "adaptive_shadow", "adaptive_live"
    weights: dict[str, float]
    min_coverage: float
    missing_policy: str       # "cash", "impute_neutral", "renormalize_capped"
    created_at: datetime
    source: str               # "default", "ic_engine", "manual_override"

def load_live_weight_policy(as_of: date, horizon: str) -> WeightPolicy:
    # read signal_weight_current if enabled
    # otherwise return versioned static baseline
```

Then change both cron paths:

```python
policy = load_live_weight_policy(as_of=today, horizon="5d")
card = combine_with_policy(signals, policy)
```

Do not immediately let adaptive weights fully control production. Use three modes:

1. **static_baseline** — current behavior, but versioned and logged.
2. **adaptive_shadow** — compute adaptive composite side by side, store both.
3. **adaptive_live_guarded** — use adaptive weights with constraints.

For adaptive live, use guarded weights, not raw IC hard drops:

```python
score_i = shrink(ICIR_i, toward=0, strength=n_eff)
score_i = max(score_i, 0)  # unless shorting/contrarian signal explicitly allowed
weight_i = floor_i + budget * softmax(score_i / temperature)
weight_i = cap_change(weight_i, previous_weight_i, max_delta=0.05)
```

Also handle missing signals explicitly. Replace full renormalization with one of:

- **cash bucket:** unavailable weight stays unused; composite confidence/coverage falls.
- **neutral imputation:** missing `z` becomes 0, but confidence and coverage decline.
- **capped renormalization:** redistribute only up to a maximum multiplier, e.g. no surviving signal can exceed 1.25x its policy weight.

For a rating engine, I would choose neutral imputation plus coverage penalty:

```python
effective_z_i = 0 if missing else z_i
coverage = sum(policy.weights[i] for i in observed) / sum(policy.weights.values())
composite = sum(policy.weights[i] * effective_z_i for i in all_signals)
composite_adj = composite * sqrt(coverage)
```

That prevents an off-panel stock from accidentally receiving a high-conviction rating from three noisy survivors.

#### Honest trade-off

Wiring adaptive weights will likely make the product look worse before it gets better:

- factor and technicals may collapse in importance,
- ratings will change,
- historical UI continuity breaks,
- users may see fewer strong BUY/SELL names because coverage-adjusted composites shrink.

But that is the correct pain. The alternative is a research engine that knowingly ignores its own evidence.

---

### 2. **The system fuses signals with incompatible horizons into one 5d rating**
**Layer / mechanism:** signal schema, `combine.py`, `map_to_tier`, `compute_walk_forward_ic`, supply_chain, factor, technicals, premarket, macro.

The current design assumes that all signal `z` values are commensurable. They are not.

A single composite is mixing:

- factor: likely medium-term cross-sectional expected return,
- technicals: possibly short-term reversal/momentum,
- analyst: slower-moving revisions / sentiment,
- earnings: event-driven,
- news: short-lived,
- premarket: intraday,
- macro: broad regime context,
- supply_chain: multi-month fundamental bottleneck thesis,
- insider: sparse, slow, episodic.

Then the validation layer evaluates them mostly against **5d forward rank IC**.

That is not just imperfect. It can invert conclusions.

A good 3-month factor may look bad over 5d. A premarket signal may be useless by close+5d even if useful intraday. Supply-chain risk may take quarters to manifest. News may decay in hours. The system currently treats negative 5d IC as if it means “bad signal,” when it may mean “wrong horizon” or “wrong decay.”

#### Why it matters concretely

This creates several failure modes.

First, the adaptive subsystem may be correctly measuring 5d performance but wrongly governing multi-horizon signals. If factor is designed for 20–60d and is punished on 5d IC, the weight engine will discard potentially useful slower alpha.

Second, the tier thresholds become arbitrary. `map_to_tier` says:

- composite > 1.5 = BUY,
- > 0.5 = OVERWEIGHT,
- >= -0.5 = HOLD,
- etc.

But a composite of 0.8 means different things depending on whether it comes from:

- one strong supply-chain score,
- three tactical signals,
- a stale factor value,
- analyst revisions,
- a premarket gap signal.

There is no expected-return unit, no holding-period unit, and no uncertainty unit. The rating tier looks precise but is not tied to a coherent forecast.

Third, the confidence layer is structurally weak. Calibrating confidence to 5d directional hit rate produces something near 50%, which is expected for equity direction. That does not mean the engine has no value; cross-sectional alpha can exist with near-50% directional hit rate. But as currently defined, confidence is not measuring what the product needs.

A rating engine needs something closer to:

- probability of outperforming universe/sector over horizon,
- expected excess return,
- expected drawdown / dispersion,
- confidence interval around rank,
- data coverage / staleness quality.

Directional “up/down in 5 days” is a poor confidence target for cross-sectional stock selection.

Fourth, `agreement = 1/(1+var(z))` is not robust. Low variance among weak or stale signals can produce high agreement. Three mediocre signals all at +0.2 are not “high agreement” in an economically meaningful sense. Likewise, one high-quality slow signal and one irrelevant intraday signal can mechanically reduce agreement despite no real contradiction.

#### Concrete optimization

Split the engine into **horizon-specific sleeves** and only then produce an aggregate display rating.

Recommended sleeves:

```text
intraday / 1d:
    premarket, very short-term technicals, breaking news

5d tactical:
    technicals, earnings drift, news, options, analyst revisions

20d-60d intermediate:
    factor, analyst, earnings, insider, selected technical momentum/reversal

60d-180d strategic:
    factor, supply_chain, macro regime, insider, fundamental revisions
```

Extend `SignalScore`:

```python
class SignalScore(TypedDict):
    ticker: str
    z: float | None
    raw: Any
    confidence: float
    as_of: datetime
    source: str
    horizon_days: int
    half_life_days: float
    valid_until: datetime
    data_timestamp: datetime
    pit_timestamp: datetime
    coverage: float
    error: str | None
```

Then compute separate composites:

```python
composite_5d = combine(signals where horizon compatible with 5d, weights_5d)
composite_20d = combine(signals where horizon compatible with 20d, weights_20d)
composite_60d = combine(signals where horizon compatible with 60d, weights_60d)
```

Store them separately:

```sql
rating_cards (
    ticker,
    as_of,
    composite_1d,
    composite_5d,
    composite_20d,
    composite_60d,
    rating_5d,
    rating_20d,
    rating_60d,
    display_rating,
    weight_policy_id,
    coverage_score,
    freshness_score
)
```

For the UI, avoid pretending there is one universal truth. Show:

```text
AAPL
Tactical 5d: HOLD
Intermediate 20d: OVERWEIGHT
Strategic 60d: BUY
Overall: OVERWEIGHT, horizon-mixed
```

Validation should become a horizon matrix:

```text
signal x horizon:
    1d IC
    5d IC
    10d IC
    20d IC
    60d IC
    decile spread
    turnover
    hit rate vs universe
    hit rate vs sector
    t-stat with overlapping-return adjustment
```

Important: 5d forward returns overlap heavily if computed daily with `LEAD(close,5)`. Your ~8000 observations are not independent. The IC t-stats and confidence should use Newey-West or block bootstrap by date. Otherwise the system will overstate statistical certainty.

For factor specifically, do not decide its value from only 5d IC. Run:

```text
factor IC at 5d, 10d, 20d, 60d
sector-neutral IC
size-neutral IC
long-only top-minus-bottom quintile return
within-sector rank IC
regime splits
```

If factor is negative at every horizon and neutralization, reduce or rebuild it. If it is bad only at 5d, move it out of the 5d composite.

#### Honest trade-off

This adds product and data complexity. The UI becomes less simple than a single BUY/HOLD/SELL card. Backtests are more expensive. Weight governance must exist per horizon.

But it fixes the core conceptual problem: a multi-horizon research engine cannot be honestly evaluated, fused, and explained as one 5d directional model.

---

### 3. **The data architecture is too fragile and not point-in-time enough for a research engine**
**Layer / mechanism:** `SP500_UNIVERSE` static parquet; factor panel; supply_chain scorecard; live API fan-out; GitHub Actions crons; Vercel serverless; `safe_fetch`; dual entry `api/index.py` vs `alpha_agent/api/app.py`.

The system has research ambitions but a data pipeline closer to a live scraping app.

Current issues:

- static S&P 500-like universe parquet,
- off-panel names lose factor through `KeyError`,
- point-in-time membership exists only in factor backtest,
- supply_chain has no point-in-time history,
- many signals call live APIs per ticker per cron,
- transient yfinance TLS failures around 6% per pass,
- China → Vercel curl frequently times out,
- serverless time cap drives shard compromises,
- two API registration paths can drift,
- errors are caught selectively and can convert data problems into dropped signals.

#### Why it matters concretely

The largest hidden risk is not that a cron fails. It is that the system produces **plausible but non-reproducible ratings**.

If a card says MSFT was BUY on a date, can you reconstruct exactly:

- which universe was used,
- which signal values were available,
- which provider responses were used,
- which weights were live,
- which data failed,
- which unavailable signals were excluded,
- whether the ticker was in the factor panel,
- whether supply_chain was known as of that date?

Right now the answer is probably “partially.”

That damages both research and user trust. If the engine improves or degrades, you may not know whether alpha changed or data availability changed.

The static universe is a material research flaw. A current snapshot creates survivorship bias in backtests and coverage bias in live cards. Even if this is “only” a rating engine, survivorship will inflate historical quality and distort factor IC.

Supply_chain is the clearest example: it has a current snapshot with no PIT history and a live exploratory 0.05 weight. That means:

- it cannot be cleanly backtested,
- its score may embed later knowledge,
- scored names receive an extra signal unavailable to others,
- the score has author/research-process risk,
- the live engine assigns it the same nominal weight as macro/options/premarket despite no forward evidence.

The API fan-out problem also feeds directly into ranking quality. A 6% transient failure rate per ticker-signal pass is not operational noise; under renormalization, it changes the composite. Failed data becomes model variation.

#### Concrete optimization

Build a minimal **point-in-time feature store** before adding more signals.

Tables:

```sql
universe_membership (
    universe_id text,
    ticker text,
    effective_from date,
    effective_to date,
    source text,
    is_member boolean,
    metadata jsonb,
    primary key (universe_id, ticker, effective_from)
);

raw_provider_observations (
    provider text,
    endpoint text,
    ticker text,
    requested_at timestamptz,
    as_of timestamptz,
    payload_hash text,
    payload jsonb,
    status text,
    error text,
    latency_ms int,
    primary key (provider, endpoint, ticker, requested_at)
);

signal_observations (
    signal_name text,
    ticker text,
    as_of timestamptz,
    data_timestamp timestamptz,
    z float,
    raw jsonb,
    confidence float,
    coverage float,
    error text,
    code_version text,
    input_hash text,
    primary key (signal_name, ticker, as_of)
);

rating_observations (
    ticker text,
    as_of timestamptz,
    horizon_days int,
    composite float,
    rating text,
    confidence float,
    coverage float,
    weight_policy_id text,
    signal_set_hash text,
    code_version text,
    primary key (ticker, as_of, horizon_days)
);
```

Then change the pipeline from:

```text
cron -> per ticker live fetch -> signal -> combine -> card
```

to:

```text
provider ingestion -> raw tables
signal materialization -> signal_observations
weight policy load -> rating materialization
API reads materialized cards
```

The live API should not be fetching primary market data per card. It should mostly serve cached materialized outputs.

For crons:

- move scheduled execution to a single region close to providers and DB,
- make jobs idempotent by `(job_id, ticker, signal, as_of)`,
- use retry with exponential backoff and jitter,
- record hard failure vs stale carry-forward,
- add provider-level circuit breakers,
- separate ingestion failures from signal failures,
- alert on coverage deltas, not only job status.

For `safe_fetch`, keep not catching generic `Exception` in development, but in production you need a top-level circuit that records unexpected failures without killing whole shards:

```python
try:
    signal = fetch_signal(...)
except KnownExternalError as e:
    return missing_signal(error_type="external", retryable=True)
except Exception as e:
    record_unexpected_exception(signal_name, ticker, as_of, traceback)
    return missing_signal(error_type="internal", retryable=False)
```

The difference is important: do not silently swallow internal bugs, but do persist the failure and continue the batch.

Unify the API entrypoints. `api/index.py` should import the same `create_app()` used by `alpha_agent/api/app.py`. Router registration in two places is pure operational debt.

```python
# api/index.py
from alpha_agent.api.app import create_app

app = create_app()
```

No second router list.

#### Honest trade-off

This is less glamorous than adding new signals. It creates more tables, more job state, and more boring monitoring. But without it, ICs, ratings, and user-visible cards remain contaminated by data availability, stale panels, and provider randomness.

---

## Additional critique by subsystem

### Fusion and missingness

`combine.py` being pure and well-tested is good. The issue is the policy embedded in it: dropping zero-confidence, zero-weight, or non-finite signals and renormalizing survivors is too optimistic.

For a research/rating engine, missing data should reduce confidence and often shrink the composite. It should not increase the importance of whatever happened to return.

Concrete change:

- keep `combine()` as a low-level math primitive,
- add `combine_with_policy()` above it,
- make missingness behavior explicit,
- store `coverage_weight`, `num_signals_observed`, and `missing_high_weight_signals`.

Example card metadata:

```json
{
  "coverage_weight": 0.62,
  "missing_signals": ["factor", "news"],
  "composite_raw": 0.91,
  "composite_coverage_adjusted": 0.72
}
```

That is much more honest than a naked OVERWEIGHT.

---

### Rating thresholds

`map_to_tier` thresholds are arbitrary unless tied to historical realized outcomes.

A composite of +0.5 becoming OVERWEIGHT only means something if historical +0.5 names have produced positive forward excess return after turnover and sector effects.

Better calibration:

```text
For each horizon:
    bucket composite into quantiles or calibrated score bins
    estimate forward excess return vs universe/sector
    estimate drawdown / dispersion
    map tiers to expected excess return and confidence interval
```

Example:

```text
BUY = top 10% of calibrated 20d expected excess return, subject to coverage > 0.75
OVERWEIGHT = 60th-90th percentile
HOLD = 40th-60th
UNDERWEIGHT = 10th-40th
SELL = bottom 10%
```

This will make tiers more stable and interpretable.

Trade-off: tier counts become relative. In a weak market, you may still have BUYs unless you add an absolute market/macro overlay.

---

### Hysteresis

Tier hysteresis suppresses threshold wobble, which is useful, but it can also hide meaningful deterioration.

The hysteresis rule should depend on:

- signal freshness,
- magnitude of composite change,
- whether the prior tier was based on stale/missing data,
- whether a high-weight signal appeared/disappeared.

Recommended:

```python
if coverage_today < min_coverage:
    rating = "INSUFFICIENT_DATA" or downgrade confidence

elif abs(composite_today - composite_yesterday) > shock_threshold:
    bypass_hysteresis

elif high_weight_signal_changed:
    reduce hysteresis band

else:
    apply normal hysteresis
```

---

### Confidence

The current confidence concept is weak and potentially harmful if used for Kelly sizing.

A 50%-ish calibrated directional hit rate is not a useful single-user equity-rating confidence measure. Worse, using that for Kelly sizing is dangerous because Kelly needs:

- expected return,
- payoff distribution,
- variance,
- drawdown tolerance,
- correlation with existing holdings,
- estimation error.

A 51% directional probability with small average win and large average loss is not a positive Kelly bet. A 49% directional hit rate with large upside and small downside can be attractive.

Replace current confidence with multiple displayed quantities:

```text
model_confidence: statistical reliability of the forecast
data_confidence: coverage + freshness + provider quality
cross_signal_agreement: directional breadth among compatible signals
calibrated_edge: expected excess return bucket
```

If you keep one public number, define it as:

```text
Confidence = reliability that the stock belongs in its assigned rank bucket over the chosen horizon.
```

Do not use it for Kelly unless you build a proper expected-return and risk model.

---

### Supply chain signal

The supply_chain integration is promising but prematurely promoted.

Problems:

- 10 names only,
- no point-in-time score history,
- no clean backtest,
- hand-authored research process,
- current snapshot can embed look-ahead,
- weight 0.05 is unvalidated,
- unscored names get `z=None`, causing coverage asymmetry.

Concrete fix:

- set live production weight to 0 until at least a minimum forward sample exists,
- continue collecting forward IC,
- snapshot every score revision with `valid_from`, `valid_to`, `author`, `evidence_hash`, `methodology_version`,
- require scored and unscored treatment to be explicit.

Schema:

```sql
supply_chain_scorecard_history (
    ticker text,
    valid_from timestamptz,
    valid_to timestamptz,
    score float,
    z float,
    rubric jsonb,
    evidence_refs jsonb,
    methodology_version text,
    author text,
    created_at timestamptz,
    primary key (ticker, valid_from)
);
```

Until validated, use it as explanatory/contextual, not as a fused alpha contributor.

---

### Universe

The static parquet universe is a bigger issue than it may look.

Live effects:

- new names like VRT lose factor,
- delisted/replaced names are absent from historical view,
- factor panel and rating universe diverge,
- universe membership affects rank IC and cross-sectional z-scoring.

Concrete fix:

- create `universe_membership` as described above,
- use the same PIT universe in live rating and backtesting,
- mark off-panel names explicitly,
- do not silently drop factor due to `KeyError`.

For off-panel names:

```python
if ticker not in factor_panel:
    return SignalScore(
        z=0,
        confidence=0,
        coverage=0,
        error="not_in_factor_panel",
        ...
    )
```

Then the rating card should show:

```text
Factor unavailable: ticker not in factor panel.
Coverage-adjusted composite applied.
```

---

### Backtest methodology

The current IC machinery is useful but insufficient.

5d Spearman rank IC is a good diagnostic, not a full objective.

You need at least:

1. **Horizon matrix:** 1d, 5d, 10d, 20d, 60d.
2. **Sector-neutral IC:** because equity ratings often become sector bets otherwise.
3. **Size/liquidity neutral IC:** especially for S&P-ish universe with off-panel extras.
4. **Decile/quintile spread:** users care whether top-rated names beat lower-rated names.
5. **Turnover:** a high-IC signal that completely reshuffles daily may be unusable.
6. **Breadth-adjusted t-stats:** overlapping 5d returns reduce effective sample size.
7. **Signal availability conditioning:** measure IC only where the signal was actually available live.
8. **Composite attribution:** whether each signal improves or degrades the fused model.

Also, `LEAD(close,5)` should be checked for:

- corporate actions,
- dividends,
- split adjustment,
- market holidays,
- missing prices,
- stale closes,
- whether returns are close-to-close or next-open-to-close.

For a displayed rating generated after market close, close-to-close may be acceptable. For intraday cards, using same-day close could introduce timing ambiguity unless `as_of` is precise.

---

### Analyst signal

Analyst is the only clearly positive signal in the observed 5d ICs and is underweighted at 0.10.

This deserves immediate investigation:

- Is it truly alpha, or a proxy for post-earnings drift / mega-cap momentum?
- Is there look-ahead in analyst timestamps?
- Is coverage biased toward large/liquid names?
- Does it survive sector-neutralization?
- Does it decay after 5d, 20d, 60d?
- Is the positive IC driven by a few dates?

If it passes those tests, it should receive more weight in the 5d tactical sleeve.

---

### Technicals

Technicals at -0.062 / -0.090 5d IC are bad enough to demand immediate action.

Do not merely reduce weight. First determine whether the sign is wrong.

Common causes:

- momentum signal accidentally rewards overbought names over a reversal horizon,
- z-score sign convention inverted,
- lookback horizon mismatched,
- close-to-close forward return punishes intraday continuation signals,
- sector/market beta contamination,
- signal computed using stale or misaligned bars.

Concrete debugging:

```text
For technicals:
    plot IC by component
    test sign flip
    test 1d, 3d, 5d, 10d, 20d horizons
    split by volatility regime
    split by market up/down days
    compare close-to-close vs next-open-to-close
```

If sign-flipped technicals have positive IC, the module likely has a convention or horizon error. If all are negative, drop from 5d live weight.

---

### Factor signal

Factor at 0.30 live weight with negative 5d IC is the biggest single static-weight risk.

But do not immediately kill factor globally. It may be mis-horizoned.

Test:

```text
factor 5d IC
factor 20d IC
factor 60d IC
factor within-sector IC
factor beta-neutral IC
factor value/growth/quality/momentum component IC
factor top-minus-bottom quintile return
```

If factor remains negative across horizons, then either:

- the factor definition is stale,
- the cross-sectional z construction is wrong,
- the universe/panel is biased,
- the signal is overfit,
- the current regime is hostile.

If it is positive at 20d/60d, move it out of the 5d tactical card and into strategic rating.

---

### News / LLM sentiment

BYOK read-time LLM sentiment is structurally inconsistent with scheduled rating production.

If no global key exists in prod, then news sentiment cannot be a stable backend alpha input unless you precompute it with a system key or exclude it from production weights.

Do not allow user-supplied read-time LLM analysis to affect shared backend picks. It will be non-reproducible and user-specific.

Recommended split:

- backend news signal: deterministic, precomputed, system-owned, stored;
- user BYOK persona explanations: display-only, not alpha;
- if no backend key, set production news weight to 0 and show unavailable.

---

### Frontend/client-side factor toggle

The client-side SHORT/LONG factor-mode toggle recomputing display via localStorage is dangerous if it looks like it changes backend picks.

It is fine as a sandbox, but the UI should label it clearly:

```text
Personal what-if view. Does not affect backend picks, rankings, or stored ratings.
```

Otherwise users will think they changed the model when they only changed display math.

---

### Persona registry dual-source

Backend registry plus hardcoded frontend persona list is low-value drift risk. Remove the hardcoded frontend list. This is not alpha-critical but is easy hygiene.

---

## Mis-prioritization

### Too much effort appears spent on low-value / premature subsystems

1. **Adaptive weights fully built before production policy integration.**  
   The hard part is not computing IC; it is governing how IC changes live decisions. The current subsystem stops before the valuable part.

2. **Supply-chain research layer before PIT history and validation.**  
   Author-grade research may be useful, but without PIT snapshots and forward validation, it should not receive live alpha weight.

3. **Political/geopolitical display-only signals.**  
   If weight is zero and no validated return path exists, they are explanatory content, not quant infrastructure.

4. **Persona/explanation UI complexity.**  
   Useful for product feel, but lower priority than reproducible ratings, weight governance, data quality, and objective alignment.

5. **Client-side personal weight editor.**  
   Nice sandbox, but it risks confusing the distinction between personal display and backend model. It also does not solve the production model problem.

### Missing or underbuilt high-value pieces

1. **Point-in-time feature store and reproducibility.**
2. **Horizon-specific validation and ratings.**
3. **Production weight policy layer.**
4. **Coverage/staleness-aware fusion.**
5. **Composite attribution and degradation monitoring.**
6. **Sector-neutral and risk-neutral evaluation.**
7. **Provider ingestion cache with retries and audit trail.**
8. **Clear forecast target: excess return, rank bucket, or directional move.**

---

## Methodology-level questions

### Is 5d rank IC the right objective?

Partially. It is a useful diagnostic for tactical cross-sectional ranking. It should not be the sole objective for the whole engine.

Use 5d IC for signals intended to rank stocks over the next week. Do not use it to judge supply_chain, macro, insider, or medium-term factor signals without horizon-specific tests.

Better objective set:

```text
Primary:
    forward excess return rank IC by horizon

Secondary:
    top-minus-bottom quintile spread
    rating bucket realized return
    sector-neutral IC
    turnover-adjusted spread
    drawdown of top bucket
    calibration of expected return by score
```

### Is the factor signal mis-horizoned?

Very likely possible. A factor signal with negative 5d IC but high static weight is either:

- mis-horizoned,
- stale,
- sign-inverted,
- improperly normalized,
- regime-impaired,
- or genuinely useless.

You cannot decide from 5d alone. Test 20d and 60d immediately. If factor is still negative there, cut it hard or rebuild.

### Is the technical signal broken?

Possibly. The observed negative 5d IC is large enough that I would treat technicals as suspect, not merely weak.

Immediate test: sign-flip technicals and rerun IC. If sign flip works, there is likely a construction or horizon convention error.

### Is the inert adaptive-weight subsystem worth wiring or removing?

Wire it, but not directly.

Do not allow the current hard-drop outputs to instantly control live production. Instead:

1. load adaptive weights into shadow live cards,
2. store static and adaptive composites side by side,
3. compare realized 5d/20d outcomes for 4–8 weeks,
4. then promote guarded adaptive weights if they outperform.

If the team will not wire it into the decision path, remove it from production-facing methodology. A shadow system that contradicts live behavior is worse than no system because it creates false confidence.

### Is confidence around 50% useful?

Not as currently defined.

For directional 5d hit rate, 50% is expected and not very informative. For Kelly sizing, it is actively dangerous unless paired with payoff distribution and risk.

Replace with:

- data confidence,
- model confidence,
- expected excess return bucket,
- rank stability,
- coverage score.

If a single number is required, make it “confidence in rating bucket,” not “probability the stock goes up.”

### Is the signal set mis-horizoned?

Yes. The architecture currently says “13 signals,” but economically they are not one peer group. They are a mixture of tactical, event, structural, and explanatory signals. Treating all as same-horizon z-scores is the major research design problem.

### Is supply_chain ready for live weight?

No. Keep it visible as research context, but set production weight to 0 until forward evidence exists and PIT history is stored.

### Is the current rating useful?

Potentially, but only as a heuristic composite. It is not yet a validated, horizon-coherent expected-return rating.

---

## OPTIMIZATIONS

1. **Wire a production `WeightPolicy` loader into `fast_intraday` and `slow_daily`, with static/adaptive/shadow modes and every card storing `weight_policy_id`.**

2. **Replace survivor renormalization with coverage-aware fusion: missing high-weight signals should shrink composite/confidence, not amplify remaining signals.**

3. **Split ratings into horizon sleeves — 1d, 5d, 20d, 60d — and validate each signal only against compatible horizons.**

4. **Immediately shadow-test adaptive weights versus static weights live for 4–8 weeks before promoting guarded adaptive weights.**

5. **Run factor and technical diagnostic IC matrices across 1d/5d/20d/60d, including sign-flip, sector-neutral, and component-level tests.**

6. **Set supply_chain production weight to 0 until PIT score history and forward IC/decile evidence exist.**

7. **Build PIT tables for universe membership, raw provider observations, signal observations, and rating observations.**

8. **Move live API fan-out into provider ingestion/materialization jobs; make the API serve cached rating cards, not perform fragile data acquisition.**

9. **Unify `api/index.py` and `alpha_agent/api/app.py` so there is only one FastAPI router registration path.**

10. **Replace directional 5d confidence/Kelly with data confidence, model reliability, expected excess return bucket, and coverage score.**

11. **Calibrate tier thresholds from historical forward excess-return buckets rather than fixed composite cutoffs.**

12. **Add composite attribution reports showing which signals improved or hurt realized forward outcomes by date, sector, and horizon.**

13. **Treat BYOK LLM news/persona features as display-only unless backend news sentiment is precomputed, stored, and reproducible.**

14. **Add data-quality monitoring on coverage deltas, stale signals, provider failure rates, off-panel tickers, and changed universe membership.**

15. **Remove or demote display-only zero-weight political/geopolitical/persona complexity until core rating reproducibility and validation are fixed.**

## VERDICT

Architecturally promising but currently misaligned: the system has