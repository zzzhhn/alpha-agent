## 1. Highest-confidence issues: where multiple audits converge

| Finding | Audits | My judgment | Why it is high-confidence |
|---|---:|---|---|
| **Live weights are disconnected from research/adaptive weights** | A, B, C | **Real, severe** | All three identify that live crons still consume `DEFAULT_WEIGHTS`, while `signal_weight_current` / adaptive outputs are inert. This is not cosmetic: the production rating is not governed by the validation layer. |
| **Static live weights overweight signals with bad observed 5d IC** | A, B, C | **Real, but interpretation needs nuance** | Factor/technicals/news being negative while still weighted is a real production risk. But “negative 5d IC” is not automatically proof factor/supply-chain are bad; it may prove the evaluation horizon is wrong. Technicals are more suspect because 5d is plausibly their native horizon. |
| **Universal 5d IC is horizon-incoherent** | A, B, C | **Real, architectural** | Factor, supply chain, insider, analyst, premarket, news, and technicals are not one-horizon signals. A single 5d validation target can misclassify slow signals and over-credit/under-credit short-lived signals. |
| **Missing-signal renormalization silently mutates the model** | A, B | **Real, severe** | If factor/news/options/etc. fail or are unavailable, remaining signals inherit their weight. That turns data availability into alpha. It also means two tickers can receive the same rating label from materially different effective models. |
| **Static/current universe causes survivorship and off-panel problems** | A, B, C | **Real, severe** | A static S&P-ish parquet plus off-panel `KeyError` for factor is both a backtest bias and live coverage bug. Universe membership and factor coverage must be point-in-time and explicit. |
| **Supply-chain signal is not production-ready as alpha** | A, B, C | **Real** | 10 names, no PIT score history, no forward sample, hand-authored process. It can be contextual research; it should not silently contribute to production composite weight. |
| **Confidence / Kelly usage is conceptually wrong** | A, B, C | **Real** | A ~50% directional hit-rate confidence is not an equity-rating confidence measure and is not sufficient for Kelly sizing. Kelly needs expected return, payoff distribution, variance, correlations, and estimation error. |
| **Provider fan-out / transient failures contaminate ratings** | A, B, C indirectly | **Real** | Live per-ticker provider calls plus failure rates matter because missingness changes weights. Ops reliability is model correctness here, not merely availability. |
| **Need cached/materialized signal observations and reproducibility** | A, B partly, C partly | **Real** | If you cannot reconstruct the exact inputs, weights, code version, failures, and universe for a card, you cannot debug IC, user complaints, or model drift. |
| **Fixed tier thresholds are uncalibrated** | A, B | **Real** | `+0.5 = OVERWEIGHT` only means something if historical realized forward excess returns justify that mapping. Otherwise tiers are arbitrary labels over z-score soup. |

---

## 2. Findings that are wrong, overstated, or misread the brief

### Audit A

#### A1. “The researched policy says factor/news/technicals should be hard-dropped.”
**Overstated.**

The adaptive table may currently output zero weights, but that does **not** make it the “researched policy.” It is one noisy policy artifact derived from short, overlapping 5d IC windows. Treating it as truth would be another architecture error.

Correct reading:

- Live static weights ignoring evidence is bad.
- Raw adaptive hard-drops are also unsafe.
- The right fix is **versioned weight policy + shadow adaptive + constrained shrinkage**, not blindly promoting `signal_weight_current`.

#### A2. “The composite is likely anti-aligned with the empirical 5d objective.”
**Mostly true for the 5d tactical sleeve, overstated for the whole product.**

If the displayed product is explicitly a 5d rating, then yes: overweighting negative-IC 5d signals is a direct issue.

But if factor, supply-chain, insider, or macro are intended as 20d–180d signals, then 5d IC cannot condemn them globally. It can only say: **do not let them dominate the 5d tactical card.**

#### A3. “Use neutral imputation plus coverage penalty.”
**Directionally right, but not universally right.**

Neutral imputation is good for many normalized signals. But some signals are conditionally available by design:

- earnings signal only around events,
- options signal only where options liquidity exists,
- insider signal only after filings,
- supply-chain only for researched coverage names.

For those, missingness can mean different things:

- structurally not applicable,
- provider failure,
- stale,
- not in coverage universe,
- genuinely no event.

Those cases should not all become `z = 0`. The missingness taxonomy matters.

#### A4. “Move scheduled execution to a single region close to providers and DB.”
**Reasonable, but not the main architectural fix.**

This helps latency/reliability. It does not solve the core problem unless paired with persisted raw observations, idempotent jobs, retries, staleness flags, and non-renormalizing fusion.

---

### Audit B

#### B1. “Cut technicals from 0.20 immediately.”
**Probably right, but too absolute.**

Technicals at materially negative 5d IC deserve immediate action. But the first action should be:

1. check sign convention,
2. check close/open alignment,
3. check component ICs,
4. check 1d/3d/5d/10d horizons,
5. check whether the IC is driven by one component.

If sign-flipped technicals work, this is a bug, not an alpha conclusion.

Practical answer: **cap or zero technicals in the 5d live policy immediately unless/until diagnostics clear.** Do not merely “move weight to analyst” without checking analyst timestamp leakage and sector/mega-cap bias.

#### B2. “N≈16 effective observations.”
**Directionally useful, numerically too glib.**

The point is valid: daily 5d forward returns overlap, so 8,000 ticker-date observations are not independent.

But saying “N≈16” ignores cross-sectional breadth. The effective sample is not simply four months divided by five days. It is closer to a time-series of cross-sectional ICs with autocorrelation and cross-sectional dependence. You need Newey-West/block bootstrap by date, not a hand-waved N.

#### B3. “Factor is almost certainly mis-horizoned, not mis-built.”
**Overconfident.**

Factor may be mis-horizoned, but it could also be:

- sign inverted,
- contaminated by current universe membership,
- stale,
- sector/size beta in disguise,
- improperly winsorized/z-scored,
- broken for off-panel names,
- regime-impaired.

The right claim: **5d IC alone cannot distinguish mis-horizon from broken construction.**

#### B4. “Display-only weight-0 political/geopolitical signals cost nothing.”
**Wrong product/ops instinct.**

Even zero-weight signals cost:

- UI complexity,
- user trust,
- explanation drift,
- maintenance burden,
- possible implied causality,
- future accidental promotion risk.

They may be low compute cost, but they are not zero architectural cost. Keep only if clearly labeled as context and excluded from model provenance.

#### B5. “Keep supply_chain at 0.05 exploratory.”
**Wrong if it affects production ratings.**

A 0.05 weight sounds small, but for a sparse scorecard it creates unequal coverage treatment. With renormalization and only 10 names, it can distort exactly the names where the model has the least statistical evidence.

Better:

- production alpha weight: **0**,
- shadow/contextual display: yes,
- promote only after PIT history + forward sample + coverage policy.

---

### Audit C

Audit C is the weakest audit. Its overlapping findings are mostly right; its unsupported specifics are not.

#### C1. External GitHub references are irrelevant / hallucinated.
**Wrong basis.**

Audit C cites random GitHub projects/users as if they support claims about factor horizons, validation frameworks, and survivorship bps. Those are not part of the supplied brief and do not establish anything about this architecture.

Discard those references.

#### C2. “Historical simulations overstate returns by 50–150 bps.”
**Unsupported.**

Survivorship bias is real. The numeric magnitude is invented unless measured on this universe and time period.

Correct statement: static current membership can bias backtests upward and distort IC. Magnitude unknown.

#### C3. “Wire adaptive weights immediately with circuit breakers.”
**Dangerous.**

This is the biggest bad recommendation in C. It correctly identifies the dead adaptive subsystem, then prescribes promoting it before fixing:

- horizon mismatch,
- overlapping-return significance,
- missingness,
- signal-specific validity,
- weight governance.

The suggested guard:

```python
if abs_sum(weights) < 0.3: fallback
```

is not a meaningful model-risk control. A bad but nonzero adaptive vector passes.

#### C4. “Add 0.05 floor to prevent total signal dropout.”
**Too blunt.**

A floor can force known-bad or unavailable signals to keep influencing ratings. Floors should be policy-specific and evidence-specific. Some signals should have zero production weight until validated, especially supply_chain and BYOK-derived news.

#### C5. “Replace confidence with agreement.”
**Wrong.**

Agreement is not confidence. Low variance among weak stale signals can look like agreement. High disagreement between a valid slow signal and irrelevant intraday signal may be meaningless. Agreement is one diagnostic, not a replacement for calibrated edge or data quality.

#### C6. “Transaction cost modeling / Almgren-Chriss / QP optimization” as missing priority.
**Potentially out of scope.**

If alpha-agent is only a ratings/explanation product, execution-cost modeling is secondary. If it recommends position sizing or Kelly allocations, then risk/cost modeling becomes mandatory. C does not make that distinction.

---

## 3. What all audits missed

### 1. **Data licensing and redistribution risk**
None of the audits seriously address whether the system is legally allowed to ingest, store, transform, display, or redistribute:

- yfinance-derived market data,
- analyst ratings,
- news content,
- LLM-summarized news,
- provider payloads,
- derived ratings based on licensed data.

This is not paperwork. It affects architecture:

- what raw payloads can be stored,
- retention periods,
- whether user-facing cards can show derived values,
- whether BYOK outputs can be cached,
- whether provider terms allow commercial use,
- whether audit trails can include full raw content or only hashes/metadata.

A PIT feature store that violates provider terms is not deployable.

---

### 2. **Regulatory posture: ratings may be investment advice**
The product emits BUY/HOLD/SELL-like ratings and possibly Kelly sizing. None of the audits address the regulatory boundary.

Architecture needs to decide:

- educational research vs investment advice,
- personalized vs non-personalized recommendations,
- model-disclaimer placement,
- suitability handling,
- audit logs for displayed recommendations,
- whether user-specific portfolios change the advice classification,
- whether Kelly sizing should exist at all in a consumer-facing product.

This can dominate the technical roadmap. A brilliant signal engine that creates unmanaged advice liability is not shippable.

---

### 3. **Identifier master: ticker strings are not enough**
Audits mention PIT universe, but not the deeper issue: **ticker identity.**

You need durable security identifiers and corporate-action mapping:

- ticker changes,
- mergers,
- spinoffs,
- share-class changes,
- delistings,
- bankruptcies,
- ADR/common mismatches,
- CUSIP/FIGI/PermID/vendor symbol mapping.

A PIT universe table keyed only by ticker is insufficient. Survivorship bias is not fixed until delisting returns and security identity are fixed.

---

### 4. **Strict decision-time contract**
Audits talk about `as_of`, but none state the hard rule clearly enough:

> Every signal must declare the earliest time at which it was knowable to the model.

You need separate timestamps:

- provider observation time,
- source event time,
- exchange timestamp,
- model ingestion time,
- rating decision time,
- user display time.

Without this, after-close earnings, analyst revisions, restated fundamentals, delayed news, and premarket data can leak into the wrong decision bucket.

This is especially dangerous if one cron runs after market close and labels the rating as valid for the prior close.

---

### 5. **Backfill contamination**
A PIT store alone is not enough. You also need a backfill policy.

If a provider response arrives late, a model is recomputed, or a signal bug is fixed, do you overwrite old cards? If yes, your historical “live” performance is contaminated. If no, how do you distinguish:

- production-observed rating,
- corrected research replay,
- backfilled signal,
- restated provider data,
- new model version.

Need immutable production observations plus separate replay tables.

---

### 6. **Human/manual data governance**
Supply-chain is hand-authored. The audits mention PIT history, but not governance:

- who can edit,
- review/approval workflow,
- conflict-of-interest logging,
- evidence retention,
- methodology changes,
- stale-score expiry,
- auditability of author judgments.

A hand-authored alpha signal without governance is an uncontrolled research input.

---

### 7. **Security boundary for BYOK and LLM features**
Audit A mentions reproducibility, but all miss the security model.

BYOK/persona/news features need hard isolation:

- user keys never affect shared backend ratings,
- user LLM outputs never enter global signal tables,
- prompt-injected article text cannot trigger tool/API exfiltration,
- secrets are not logged in provider payloads,
- cached user outputs are tenant-scoped,
- model explanations cannot reveal proprietary/system prompts.

This is a product security issue, not only a modeling issue.

---

### 8. **Rating semantics: absolute return vs excess return vs sector-relative**
Audits mention sector-neutral IC, but none force the product decision:

Is `BUY` supposed to mean:

- expected positive absolute return,
- expected outperformance vs S&P 500,
- expected outperformance vs sector,
- top decile within covered universe,
- favorable risk-adjusted return?

Until that is fixed, tier calibration, confidence, backtests, and user expectations remain ambiguous.

---

## 4. Re-ranked union of real findings by impact × confidence × ease

Most worth doing first, not theoretically most elegant.

### 1. **Make production weight policy explicit and versioned**
**Impact:** very high  
**Confidence:** very high  
**Ease:** high  

Stop implicit `DEFAULT_WEIGHTS` inside crons.

Do immediately:

```text
weight_policy_id = static_v1_2026_06
mode = static | adaptive_shadow | adaptive_guarded
horizon = 1d | 5d | 20d | 60d
weights = persisted JSON
missing_policy = persisted enum
```

Every rating card stores `weight_policy_id`.

This does not require trusting adaptive weights yet. It just removes hidden policy.

---

### 2. **Stop full survivor renormalization**
**Impact:** very high  
**Confidence:** very high  
**Ease:** high  

Current behavior lets missing signals amplify surviving signals. Replace with explicit missingness.

Minimum viable fix:

```text
observed_weight = sum(weights of observed signals)
coverage = observed_weight / total_policy_weight
missing_high_weight_signals = [...]
composite = sum(w_i * z_i_or_0)
composite_adj = composite * sqrt(coverage)
```

Do not present a naked BUY if 40% of the intended model was missing.

---

### 3. **Expose coverage and effective weights on every card**
**Impact:** high  
**Confidence:** very high  
**Ease:** high  

Even before rebuilding the pipeline, show:

```json
{
  "coverage_weight": 0.62,
  "observed_signals": ["analyst", "technicals", "macro"],
  "missing_signals": ["factor", "news"],
  "effective_weights": {...},
  "stale_signals": [...]
}
```

This converts silent model mutation into visible model state.

---

### 4. **Quarantine unvalidated sparse/contextual signals from production alpha**
**Impact:** high  
**Confidence:** high  
**Ease:** high  

Set production weights to zero for:

- `supply_chain` until PIT history + forward sample exists,
- BYOK/user-specific news/persona outputs,
- display-only political/geopolitical context,
- any signal with no reproducible backend observation.

They can remain in UI as context or shadow signals.

---

### 5. **Put technicals under immediate guardrail**
**Impact:** high  
**Confidence:** medium-high  
**Ease:** high  

Given the observed negative 5d IC, do not let technicals keep 0.20 live 5d weight unchecked.

Immediate policy:

```text
technicals_5d weight = min(current, small capped value)
or set to 0 in guarded 5d policy until diagnostics pass
```

Run diagnostics:

- sign flip,
- component IC,
- 1d/3d/5d/10d/20d horizons,
- close-to-close vs next-open-to-close,
- sector/beta neutral IC,
- regime splits.

If sign-flip works, fix construction. If all horizons are negative, drop/rebuild.

---

### 6. **Add signal horizon metadata and compute horizon-specific IC**
**Impact:** very high  
**Confidence:** very high  
**Ease:** medium  

Add to signal contract:

```text
native_horizon_days
half_life_days
valid_until
event_driven boolean
```

Then evaluate:

```text
signal × horizon: 1d, 5d, 10d, 20d, 60d
```

Do not use 5d IC to govern factor/supply-chain/insider globally.

---

### 7. **Split ratings into at least tactical vs intermediate/strategic**
**Impact:** very high  
**Confidence:** high  
**Ease:** medium  

Minimum product split:

```text
1d / intraday: premarket, breaking news, short technicals
5d tactical: technicals, analyst revisions, earnings drift, news
20d–60d intermediate: factor, analyst, selected technicals, insider
60d+ strategic/context: factor, supply_chain, macro, insider
```

If UI insists on one rating, it must be derived from explicit sleeves, not raw mixed z-scores.

---

### 8. **Run factor diagnostics before cutting factor globally**
**Impact:** high  
**Confidence:** high  
**Ease:** medium-high  

Factor has high live weight and negative 5d IC, but may be mis-horizoned.

Test:

- 5d/20d/60d IC,
- sector-neutral IC,
- size/liquidity-neutral IC,
- component IC,
- sign flip,
- quintile spread,
- PIT universe sensitivity,
- coverage conditioning.

Then decide whether factor belongs in 5d, 20d, 60d, or nowhere.

---

### 9. **Disable Kelly sizing from current confidence**
**Impact:** high  
**Confidence:** very high  
**Ease:** high  

Do not feed a ~50% directional hit probability into Kelly.

Replace with separate fields:

```text
data_confidence
model_reliability
coverage_score
freshness_score
expected_excess_return_bucket
rank_bucket_confidence
```

If sizing is retained, it needs expected return, volatility, correlation, drawdown limits, and estimation-error shrinkage.

---

### 10. **Materialize signal and rating observations**
**Impact:** very high  
**Confidence:** high  
**Ease:** medium-low  

Create immutable-ish tables:

```text
signal_observations
rating_observations
raw_provider_observations or provider_observation_metadata
job_runs
```

Each observation stores:

```text
as_of
data_timestamp
provider_timestamp
model_version
input_hash
code_version
weight_policy_id
coverage
error/staleness state
```

Without this, you cannot replay ratings or debug drift.

---

### 11. **Move provider calls out of user/API paths into ingestion jobs**
**Impact:** high  
**Confidence:** high  
**Ease:** medium  

Target architecture:

```text
provider ingestion → raw/provider observations
signal materialization → signal_observations
rating materialization → rating_observations
API → cached cards
```

Do not have user-facing/API card reads depend on live yfinance/news/LLM fan-out.

---

### 12. **Add retries, circuit breakers, stale-carry-forward, and coverage alerts**
**Impact:** high  
**Confidence:** high  
**Ease:** medium  

Operational failures are model failures because they change composites.

Monitor:

```text
coverage_weight by cron
missing high-weight signals
provider failure rate
stale signal count
off-panel ticker count
rating count by tier
large day-over-day rating deltas
```

Alert on coverage deltas, not just job success.

---

### 13. **Build PIT universe membership plus identifier master**
**Impact:** very high  
**Confidence:** very high  
**Ease:** low-medium  

Do not stop at:

```text
ticker, effective_from, effective_to
```

Also need durable security identity:

```text
security_id
ticker history
exchange
share class
corporate actions
delisting return
vendor mappings
```

This is bigger work, but it is foundational for credible backtests.

---

### 14. **Calibrate rating tiers from realized forward excess-return buckets**
**Impact:** high  
**Confidence:** high  
**Ease:** medium  

Replace fixed z cutoffs with empirically calibrated tiers.

Example:

```text
BUY = top calibrated expected excess-return bucket
OVERWEIGHT = above-median positive bucket
HOLD = middle bucket
UNDERWEIGHT = below-median bucket
SELL = bottom bucket
```

Do this per horizon and preferably sector-relative or benchmark-relative.

---

### 15. **Define rating target explicitly**
**Impact:** very high  
**Confidence:** very high  
**Ease:** medium  

Choose one per rating:

```text
absolute return
excess return vs SPY
excess return vs sector
rank within universe
risk-adjusted expected return
```

Right now “BUY” is semantically overloaded. This infects validation, thresholds, confidence, and UX.

---

### 16. **Adopt constrained adaptive weights only after the above guardrails**
**Impact:** high  
**Confidence:** medium-high  
**Ease:** medium  

Do not wire raw adaptive weights.

Use:

```text
adaptive_shadow first
then guarded adaptive
with floors/caps by signal class
with max daily/weekly delta
with horizon-native IC
with minimum effective sample
with fallback policy
```

Reasonable form:

```python
w_live = shrink(
    prior=static_policy,
    evidence=adaptive_policy,
    strength=n_eff,
    caps=factor_caps,
    floors=validated_floors,
    max_delta=0.05
)
```

Adaptive output should be evidence, not sovereign authority.

---

### 17. **Unify duplicate API entrypoints**
**Impact:** medium  
**Confidence:** high  
**Ease:** high  

If `api/index.py` and `alpha_agent/api/app.py` register routers separately, remove the duplication.

Use:

```python
from alpha_agent.api.app import create_app
app = create_app()
```

This is not alpha-critical, but it is cheap and prevents drift.

---

### 18. **Resolve BYOK/news reproducibility and security boundary**
**Impact:** medium-high  
**Confidence:** high  
**Ease:** medium  

Rules:

```text
backend alpha news = system-owned, deterministic, precomputed, stored
BYOK/persona news = user-specific display only
user LLM outputs never affect shared ratings
article/prompt content isolated from secrets/tools
```

---

### 19. **Add legal/licensing/regulatory review before expanding data/product surface**
**Impact:** very high  
**Confidence:** high  
**Ease:** low  

This is not a modeling fix, but it can block launch. Do it before building more provider-dependent features.

---

## Bottom-line judgment

The audits converge on the real core: **the system has decent plumbing but an invalid control loop.**

The production engine:

1. uses static weights,
2. ignores adaptive evidence,
3. evaluates mixed-horizon signals on 5d,
4. renormalizes away missingness,
5. lacks PIT/reproducible observations,
6. presents arbitrary tiers and weak confidence.

The main correction is **not** “wire adaptive weights.” That is too naive.

The correct correction is:

```text
explicit weight policy
+ coverage-aware fusion
+ horizon-specific validation
+ materialized PIT observations
+ calibrated rating semantics
+ guarded adaptive shadowing
```

Audit A is the most complete. Audit B is sharp but occasionally overconfident. Audit C is useful only where it overlaps A/B; its unsupported citations and “wire adaptive immediately” recommendation should be rejected.