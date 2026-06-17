## Final Optimization Roadmap for Alpha-Agent

**Single highest-leverage move:**  
**Install an explicit, versioned production `WeightPolicy` layer and make live ratings use it with coverage-aware fusion — not raw survivor renormalization and not raw adaptive weights.**  
This is the fastest way to stop hidden model mutation, align production with research governance, and make every rating auditable.

---

# Structural Changes — Do These First

## 1. Make production weighting explicit, versioned, and horizon-aware

**Problem:** Live crons use hidden `DEFAULT_WEIGHTS`; adaptive/research weights exist but do not govern production ratings.

**Concrete fix:**  
Create a `WeightPolicy` object/table consumed by both `fast_intraday` and `slow_daily`.

Minimum fields:

```text
weight_policy_id
mode = static | adaptive_shadow | adaptive_guarded
horizon = 1d | 5d | 20d | 60d
weights
missing_policy
created_at
source
```

Every `RatingCard` must store `weight_policy_id`.

Do **not** wire raw adaptive weights directly. Start with:

```text
static_v1 live
adaptive_shadow computed and stored side-by-side
guarded adaptive later via shrinkage/caps/floors
```

**ICE:** Impact **High** / Confidence **High** / Ease **High**  
**Consensus:** **Very high.** A/B/C all agree live weighting is severed from evidence; cross-reviews agree raw adaptive promotion is unsafe.

---

## 2. Stop full survivor renormalization; make missingness reduce conviction

**Problem:** When factor/news/options/etc. fail or are unavailable, their weight is silently redistributed to surviving signals, turning data availability into alpha.

**Concrete fix:**  
Replace full renormalization with coverage-aware fusion.

Minimum viable policy:

```python
z_i = 0 if missing else z_i
coverage = sum(weights_observed) / sum(weights_total)
composite_raw = sum(w_i * z_i for all signals)
composite_adj = composite_raw * sqrt(coverage)
```

Expose:

```json
{
  "coverage_weight": 0.62,
  "missing_signals": ["factor", "news"],
  "stale_signals": ["options"],
  "effective_weights": {...},
  "composite_raw": 0.91,
  "composite_coverage_adjusted": 0.72
}
```

Distinguish missing types:

```text
provider_failure
not_in_coverage
not_applicable
stale
event_absent
internal_error
```

**ICE:** Impact **High** / Confidence **High** / Ease **High**  
**Consensus:** **Very high.** Strongly supported by A, B, Cross-review A/B. C indirectly supports through universe/off-panel concerns.

---

## 3. Validate the IC pipeline before acting aggressively on IC numbers

**Problem:** The council debated weights using observed ICs, but the IC computation itself must first be proven point-in-time and timestamp-correct.

**Concrete fix:**  
Audit `compute_walk_forward_ic` for strict decision-time correctness.

Check:

```text
signal_as_of < forward_return_start
rating_decision_time is explicit
after-close data is not used for prior-close decisions
provider timestamps are preserved
earnings/news/analyst revisions are not leaked
LEAD(close, h) uses adjusted prices consistently
market holidays/missing closes handled
```

Add tests that intentionally inject late-arriving signals and verify they are excluded from earlier decisions.

**ICE:** Impact **High** / Confidence **Med-High** / Ease **High**  
**Consensus:** **Medium.** Cross-review B correctly surfaced this; independent audits under-emphasized it. Tie-break: do it early because every adaptive/diagnostic decision depends on trustworthy ICs.

---

## 4. Add signal horizon metadata and horizon-specific validation

**Problem:** The system evaluates all signals on 5d rank IC even though signals operate at different horizons.

**Concrete fix:**  
Extend the signal contract:

```text
native_horizon_days
valid_until
half_life_days
event_driven
data_timestamp
pit_timestamp
```

Run validation as a matrix:

```text
signal × horizon:
1d, 3d, 5d, 10d, 20d, 60d
rank IC
sector-neutral IC
decile/quintile spread
turnover
coverage-conditioned IC
Newey-West or block-bootstrap t-stat by date
```

Do not use 5d IC to govern factor, insider, macro, or supply-chain globally.

**ICE:** Impact **High** / Confidence **High** / Ease **Medium**  
**Consensus:** **Very high.** A/B/C unanimously agree universal 5d IC is horizon-incoherent.

---

## 5. Put technicals under immediate 5d guardrail

**Problem:** Technicals carry 0.20 live weight despite materially negative observed 5d IC.

**Concrete fix:**  
In the 5d tactical policy, immediately cap or zero technicals until diagnostics pass.

Recommended:

```text
technicals_5d_weight = 0 or small capped value
do not blindly reallocate all weight to analyst
unused weight can go to cash/neutral
```

Run diagnostics:

```text
sign-flip test
component-level IC
1d/3d/5d/10d/20d horizons
close-to-close vs next-open-to-close
sector/beta neutral IC
regime splits
bar alignment/staleness checks
```

If sign-flipped technicals work, fix construction. If all variants are negative, rebuild or remove from 5d.

**ICE:** Impact **High** / Confidence **Med-High** / Ease **High**  
**Consensus:** **High, with nuance.** B/C wanted immediate cuts; A/Cross-reviews caution to diagnose sign/horizon. Tie-break: guardrail now, diagnose in parallel.

---

## 6. Treat adaptive weights as advisory/shadow first, then guarded shrinkage

**Problem:** Raw adaptive weights currently contradict production, but wiring them directly would promote noisy, horizon-contaminated evidence.

**Concrete fix:**  
Run adaptive composites in shadow for each horizon.

Then, once IC pipeline and horizon metadata are fixed, promote only through constrained shrinkage:

```python
w_live = shrink(
    prior=static_policy,
    evidence=adaptive_policy,
    strength=n_eff,
    caps=signal_class_caps,
    floors=validated_floors,
    max_delta=0.05
)
```

Rules:

```text
no hard drops from short overlapping windows
no adaptive promotion without minimum effective sample
no global factor cut from 5d IC alone
store static and adaptive composites side-by-side
compare realized outcomes for 4–8+ weeks
```

**ICE:** Impact **High** / Confidence **High** / Ease **Medium**  
**Consensus:** **High on need, split on method.** C wanted immediate wiring; A/B/cross-reviews reject raw promotion. Tie-break: shadow + guarded shrinkage is the safe synthesis.

---

## 7. Quarantine sparse, unvalidated, or user-specific signals from production alpha

**Problem:** Supply-chain, BYOK/persona news, and display-only geopolitical/political signals can distort production ratings despite weak or non-reproducible evidence.

**Concrete fix:**  
Set production alpha weight to **0** for:

```text
supply_chain until PIT history + forward sample exist
BYOK/user-specific LLM outputs
persona explanations
display-only political/geopolitical context
any signal without reproducible backend observation
```

Keep them as:

```text
context
shadow signals
research annotations
explanatory UI only
```

For supply-chain, create history:

```text
ticker
valid_from
valid_to
score
z
rubric
evidence_hash
methodology_version
author/reviewer
created_at
```

**ICE:** Impact **Med-High** / Confidence **High** / Ease **High**  
**Consensus:** **High, but disputed.** A and cross-reviews favor zero production weight; B suggested labeled exploratory 0.05; Cross-review C wanted retention. Tie-break: if it affects production ratings, zero until validated; shadow is enough for forward testing.

---

## 8. Build point-in-time universe and materialized observations

**Problem:** Static universe parquet and live provider fan-out make ratings non-reproducible and introduce survivorship/off-panel bias.

**Concrete fix:**  
Implement minimum PIT/replay schema:

```text
universe_membership
security_master / identifier_map
raw_provider_observations or provider_observation_metadata
signal_observations
rating_observations
job_runs
```

Each rating observation stores:

```text
ticker/security_id
as_of
decision_time
horizon
composite
rating
coverage
weight_policy_id
signal_set_hash
code_version
provider/input hashes
error/staleness state
```

Move architecture from:

```text
API/cron → live per-ticker fetch → combine → card
```

to:

```text
provider ingestion → signal materialization → rating materialization → API serves cached cards
```

**ICE:** Impact **High** / Confidence **High** / Ease **Low-Med**  
**Consensus:** **Very high on need.** A/B/C all identify static universe/off-panel issues; A/cross-reviews emphasize reproducibility and materialization.

---

## 9. Redefine confidence and remove Kelly from current directional hit rate

**Problem:** Current ~50% directional confidence is not a reliable rating-confidence measure and is unsafe for Kelly sizing.

**Concrete fix:**  
Stop using current confidence for Kelly.

Replace one overloaded number with:

```text
data_confidence = coverage + freshness + provider reliability
model_reliability = historical stability of signal/rating bucket
rank_bucket_confidence = probability stock belongs in assigned bucket
expected_excess_return_bucket = calibrated realized forward excess-return bin
cross_signal_agreement = diagnostic only, not confidence itself
```

If sizing remains, require:

```text
expected return
volatility
correlation
drawdown limits
transaction cost/turnover
estimation-error shrinkage
```

**ICE:** Impact **Med-High** / Confidence **High** / Ease **High**  
**Consensus:** **Very high.** A/B/C agree current confidence/Kelly usage is flawed. Tie-break rejects C’s suggestion to replace confidence with simple agreement.

---

## 10. Calibrate rating tiers to explicit rating semantics

**Problem:** Fixed thresholds like `+0.5 = OVERWEIGHT` are arbitrary because the score is not tied to expected realized outcome.

**Concrete fix:**  
First define what `BUY` means:

```text
absolute positive return?
excess return vs SPY?
sector-relative excess return?
top universe rank bucket?
risk-adjusted expected return?
```

Then calibrate tiers per horizon:

```text
BUY = top calibrated expected excess-return bucket
OVERWEIGHT = above-median positive bucket
HOLD = middle bucket
UNDERWEIGHT = below-median bucket
SELL = bottom bucket
```

Use:

```text
decile/quintile spread
sector-relative performance
turnover-adjusted spread
drawdown/dispersion
coverage gates
```

**ICE:** Impact **High** / Confidence **High** / Ease **Medium**  
**Consensus:** **High.** A/B and cross-reviews support; C underweights it. Tie-break: necessary, but after IC/timestamp and horizon fixes.

---

# Nice-to-Haves / Defer Until Structural Fixes Land

These are useful, but should not distract from the control-loop and data-integrity fixes above.

1. **Full four-sleeve UI overhaul**  
   - Good direction: 1d / 5d / 20d / 60d.
   - Defer full product complexity until signal horizon validation exists.
   - Minimum now: internal horizon metadata and tactical vs intermediate distinction.

2. **Composite attribution dashboards**  
   - Valuable for research governance.
   - Build after ratings and signal observations are materialized.

3. **Persona registry cleanup and duplicate API entrypoint cleanup**  
   - API unification is cheap and should be done opportunistically:
     ```python
     from alpha_agent.api.app import create_app
     app = create_app()
     ```
   - But it is not the main rating-quality lever.

4. **Transaction cost / portfolio optimizer / QP sizing**  
   - Important only if the product recommends trades or position sizes.
   - Secondary if alpha-agent remains a ratings/explanation product.

5. **AST deduplication / factor originality checks**  
   - Potentially useful for future generated-factor research.
   - Not supported strongly enough by the supplied audits to outrank current production correctness fixes.

6. **Legal/licensing/regulatory review**  
   - Not a rating-quality optimization, but critical before broader commercial launch, especially with BUY/SELL labels, provider data, and Kelly-like sizing.

---

# Disagreements and Chairman Tie-Breaks

## Disagreement 1: Wire adaptive weights immediately vs shadow/guard them

**Positions:**
- Audit C: wire immediately with circuit breakers.
- Audits A/B and cross-reviews: do not wire raw adaptive weights; use shadow and shrinkage.

**Tie-break:**  
**Reject immediate raw adaptive wiring.**  
The adaptive system is currently trained on horizon-contaminated, overlapping 5d evidence. Wiring it directly could replace one bad policy with another. Use explicit policy + shadow + guarded shrinkage.

---

## Disagreement 2: Cut technicals immediately vs diagnose first

**Positions:**
- B/C: cut technicals now.
- A/cross-reviews: negative IC is serious, but check sign/horizon/component bugs.

**Tie-break:**  
**Cap or zero technicals in the 5d policy now; diagnose in parallel.**  
A -0.09 5d IC with 0.20 weight is too dangerous to leave untouched, but the root cause may be construction error rather than true alpha failure.

---

## Disagreement 3: Cut factor globally?

**Positions:**
- A/C sometimes imply factor is actively harmful.
- B/cross-reviews caution that factor may be mis-horizoned.

**Tie-break:**  
**Do not cut factor globally from 5d IC.**  
Remove or reduce factor from the **5d tactical** sleeve if needed, but test 20d/60d, sector-neutral, size-neutral, component IC, sign flip, and PIT universe sensitivity before cutting it from intermediate/strategic ratings.

---

## Disagreement 4: Keep supply-chain at 0.05 exploratory vs set production weight to 0

**Positions:**
- B/Cross-review C tolerate 0.05 if labeled.
- A/Cross-review A/B prefer zero production alpha weight.

**Tie-break:**  
**Set production alpha weight to 0; keep it as shadow/context.**  
A sparse 10-name, hand-authored, non-PIT signal should not move production ratings. Forward testing does not require production weight.

---

## Disagreement 5: Split into four horizon sleeves now vs just add per-signal horizons

**Positions:**
- Audit A favors full 1d/5d/20d/60d rating sleeves.
- B/Cross-review C argue this may overcomplicate product too early.

**Tie-break:**  
**Implement horizon metadata and validation now; expose at least tactical vs intermediate internally; defer full four-sleeve UI until evidence supports it.**  
The architecture must become horizon-aware, but the product does not need four public ratings on day one.

---

## Disagreement 6: Reallocate technicals weight to analyst?

**Positions:**
- B/C suggest analyst is the only positive IC signal and deserves more weight.
- Cross-review B warns analyst’s positive IC may also be noisy or leaked.

**Tie-break:**  
**Do not blindly move weight to analyst.**  
Analyst deserves investigation and possibly a guarded increase, but only after timestamp, leakage, sector/mega-cap bias, and robustness checks. Use neutral/cash weight rather than forced reallocation.

---

# Final Priority Summary

1. **Versioned production `WeightPolicy` consumed by live ratings.**
2. **Coverage-aware fusion; stop survivor renormalization.**
3. **Validate IC timestamp/look-ahead correctness.**
4. **Add horizon metadata and horizon-specific IC.**
5. **Guardrail technicals immediately.**
6. **Run adaptive weights in shadow; later promote via shrinkage.**
7. **Zero production weight for sparse/user-specific/unvalidated signals.**
8. **Build PIT universe + materialized signal/rating observations.**
9. **Replace confidence/Kelly with data/model/edge reliability fields.**
10. **Calibrate tiers to explicit expected-outcome semantics.**

Bottom line: **the system does not need more signals right now. It needs a valid production control loop: explicit weights, honest missingness, horizon-correct validation, reproducible observations, and calibrated rating semantics.**