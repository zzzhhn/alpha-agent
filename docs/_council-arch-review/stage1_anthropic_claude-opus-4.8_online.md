This is a meaty, well-documented system. Let me dig into the architecture and give you a senior-level critique. The brief is self-contained and current; I don't need external search to audit the logic here.

# DEEP CRITIQUE

## FLAW 1 — The weight layer is severed from the only evidence you have, and the static weights are anti-correlated with realized IC

This is the dominant flaw, and it's actually two flaws compounding: (a) the adaptive subsystem is inert, and (b) the static weights you actually ship are *wrong* in a measurable, directional way.

**Specifics:** `fast_intraday` fuses on `combine(sigs, DEFAULT_WEIGHTS)`, `slow_daily` on a normalized subset of the same constants. Neither reads `load_weights` / `signal_weight_current`. Meanwhile `factor` (0.30) and `technicals` (0.20) — your two largest allocations, 50% of gross weight — show near-zero-to-negative 5d rank IC (factor −0.013/−0.023, technicals −0.062/−0.090) over ~8000 obs. `analyst`, your only clearly-positive signal (+0.013/+0.026), is weighted 0.10.

**Why it matters concretely:** You are not running a neutral system — you're running a *negatively-tilted* one on half your weight. Technicals at −0.09 IC with 0.20 weight is an active bet against your own data. The composite's sign is being dragged by the two signals empirically least entitled to drive it. Every BUY/SELL tier crossing this produces is partially a function of signals that, on the evidence, hurt. The adaptive engine *knows this* — it hard-dropped factor/news/technicals to 0.0 in `signal_weight_current` — but that knowledge dies in a table no cron reads. You built the immune system and disconnected the nerves.

**The honest complication:** Do NOT just wire `apply_adaptive_weights` into the live cron. The reason it's dangerous isn't ops risk, it's *statistical*: a 4-month window with 5d-forward IC gives you ~16 non-overlapping forward observations per signal cross-sectionally (and even 8000 obs are heavily autocorrelated across the ~557-name panel — your effective N is tiny). Zeroing factor on −0.013 IC over 4 months is fitting to noise. Factor models are *designed* to pay off at 1–12 month horizons; judging them on 5d is a category error (see Flaw 3).

**Concrete optimization:**
- Don't ship the binary "wire vs remove." Ship a **constrained shrinkage blend**: `w_live = clip(0.5 * w_default + 0.5 * w_adaptive, floor=0.02, cap=2× default)`, with the adaptive component computed at the signal's *native* horizon, not 5d. This consumes the IC evidence without letting a noisy 4-month window nuke factor entirely.
- Immediately, regardless of the above: **cut technicals from 0.20.** At −0.09 IC it's the single worst risk-adjusted line in the book. Move that weight to analyst (the only positive signal) and to cash-neutral (lower gross). This is a one-line change to `DEFAULT_WEIGHTS` and is defensible *today* even under the noise caveat, because −0.09 is large and consistent across 60d/90d.
- Trade-off: shrinkage means you're never fully optimal under either the static prior or the data; you're explicitly buying robustness against a short window. That's the correct trade for N≈16.

## FLAW 2 — The objective (5d rank IC) is horizon-incoherent with the signals it's judging, so the whole evaluation layer mismeasures

**Specifics:** `compute_walk_forward_ic` uses `LEAD(close,5)` — one fixed 5d forward return — for *every* signal. But your signals operate at wildly different horizons: factor (months), supply_chain (multi-month, by your own admission), premarket (intraday), news (days), insider (weeks-to-months). You're scoring a marathon runner on a 40-yard dash and then reallocating capital based on the result.

**Why it matters:** This isn't a tuning issue, it poisons everything downstream. The `ic_engine`, the `adaptive_weights` ICIR, the `backtest` page, and any future wiring all inherit a measurement that is *correct for premarket/news and wrong for factor/supply_chain/insider*. The factor "−0.013 IC" almost certainly isn't telling you factor is broken — it's telling you factor has no 5d edge, which is *expected*. You risk amputating your most theoretically-sound signal on a measurement artifact. This is the hidden risk: the eval layer's authority exceeds its validity.

**Concrete optimization:**
- Make horizon a **per-signal property**. Add `eval_horizon_days` to each signal module's contract (premarket=1, news=3, technicals=5, analyst=10, insider=21, factor=63, supply_chain=63). `compute_walk_forward_ic(signal, window_days, horizon=signal.eval_horizon)` parameterizes `LEAD(close, horizon)`.
- Report IC per signal *at its own horizon*, and only compare ICIR (IC/std) across signals — never raw IC across mismatched horizons, since longer horizons mechanically have different IC scales and autocorrelation.
- Trade-off: longer horizons mean fewer non-overlapping obs and slower feedback (factor at 63d gives you ~2 clean obs in 4 months — basically unusable yet). The honest consequence: **factor and supply_chain cannot be IC-validated on your current data depth at all.** That's not a bug to fix with better code; it's a reason to weight them on *prior* (theory/literature) and explicitly mark them "horizon-unvalidated" rather than pretend the 5d number means something.

## FLAW 3 — The live universe is a single static parquet, creating silent survivorship bias and a hard factor-signal hole

**Specifics:** `SP500_UNIVERSE` from `factor_universe_sp500_v3.parquet`; point-in-time membership only exists in `factor_backtest`, not live. Off-panel names (VRT) throw `KeyError "not in panel universe"` and silently lose the factor signal — meaning a stock can get a rating composite assembled *without its 0.30-weighted input*, then renormalized so the remaining signals silently absorb that 30%.

**Why it matters:** Two distinct harms. (1) **Survivorship/staleness:** a v3 snapshot encodes today's membership; any backtest or IC computed against the live universe is contaminated by the fact that current members are conditioned on having survived. Your reported ICs partly inherit this. (2) **Silent weight mutation:** when factor drops via KeyError, `combine` renormalizes survivors — so VRT's rating is built on a *different effective weight vector* than AAPL's, and nothing surfaces this to the user or the eval layer. Two stocks rated on different weight schemes, presented identically. That's a correctness bug masquerading as graceful degradation.

**Concrete optimization:**
- Short term: make off-panel factor-drop **explicit in the RatingCard** (a `coverage` field: which signals fired, what the effective weight vector was). One field, high transparency value, surfaces the silent renormalization.
- Medium term: replace the single parquet with a **dated membership table** (ticker, date_added, date_removed) so live and backtest share point-in-time membership, killing the survivorship asymmetry between the two layers.
- Trade-off: dated membership requires backfilling historical constituents (vendor data or manual reconstruction) — real effort, and you'll never get it perfectly right pre-history. But the *coverage field* is cheap and removes the worst silent failure today.

---

## MIS-PRIORITIZATION

**Over-invested:** The `adaptive_weights` subsystem (EWMA-ICIR, change-cap, floor, hard-drop, shadow/promote/rollback) is a sophisticated piece of machinery that produces zero live effect. That's significant engineering — promotion/rollback state machines are not trivial — sunk into something that has *never moved a single rating*. The shadow/promote logic in particular is premature: you need a working live wire and a valid objective before promotion semantics matter. **Until Flaw 2 is fixed, every hour on adaptive weights is compounding on a broken measurement.**

**Under-invested relative to value:**
- **Confidence calibration → Kelly.** You're feeding a ~50%-by-construction confidence into Kelly sizing. Kelly at p≈0.5 with symmetric payoff sizes ≈0 — it's mathematically near-useless and potentially destabilizing near the 0.5 boundary (tiny calibration errors flip sign of the edge). This is high-risk, low-attention.
- **The ops fan-out** (per-ticker live API calls, ~6% yfinance TLS failures, China→Vercel http=000). 6% transient failure across 557 names = ~33 names with degraded/missing signals *per pass*, which feeds right back into Flaw 3's silent renormalization. This is a data-quality tax on every rating and gets less attention than the inert weight engine.

**Correctly minimal (skip):** `combine.py` is pure and well-tested — leave it. The hysteresis band is a genuinely good, cheap touch. The display-only weight-0 signals (political/geopolitical) cost nothing. The client-side parity-exact reweighter is fine as a personal tool. Don't spend effort here.

---

## METHODOLOGY-LEVEL ANSWERS

**Is 5d rank IC the right objective?** Rank IC is the right *family* (robust, scale-free, correct for a ranking engine). 5d is wrong as a *universal* horizon — see Flaw 2. The fix is per-signal horizon, not abandoning rank IC. Also consider: you care about *tier-crossing* quality, not raw IC. A signal can have low IC but high decile-spread (good tails, noisy middle) — that's what actually matters for a 5-tier rating. **Add decile top-minus-bottom spread as a co-objective; it's closer to what the product does than IC.**

**Is the factor signal mis-built or mis-horizoned?** Almost certainly mis-*horizoned*, not mis-built — you cannot conclude "broken" from a 5d window. But verify it isn't *also* mis-built: check whether the factor z is being computed cross-sectionally point-in-time or leaking the panel's current composition. The off-panel KeyError suggests the panel is a snapshot, which raises a look-ahead concern in the factor scores themselves.

**Is the inert adaptive subsystem worth wiring or removing?** Neither as-is. **Demote it to advisory, not autonomous:** keep it computing, surface its weights on the `evolution`/`methodology` page as a recommendation, but gate live consumption behind the horizon fix and the shrinkage blend (Flaw 1). Removing it discards real work; wiring it as-built lets a noisy 4-month window zero your most-principled signal. Advisory-with-shrinkage is the middle path.

**Is confidence ~50% useful?** As a *probability* fed to Kelly — no, it's actively misleading near the boundary. As a *relative dispersion signal* — maybe. **Decouple the two uses:** keep isotonic-calibrated confidence as a UI honesty indicator ("we're not sure"), but do not feed a ~0.5 directional probability into Kelly. If you want sizing, derive it from `agreement` (signal concordance) and historical decile-spread, not from a coin-flip-calibrated hit rate. Right now confidence creates a false impression of edge precision it doesn't have.

**supply_chain weight 0.05:** A guess with no forward validation and *no point-in-time history is structurally unbacktestable* — you correctly flagged this. Keep it at 0.05 exploratory and label it "prior-only, unvalidated" in the card, but understand the forward-IC tracker won't yield a usable number for months (10 names, 63d horizon → essentially no clean obs this year). Don't let it grow weight until it earns it.

---

## OPTIMIZATIONS
1. Cut `technicals` from 0.20 (−0.09 IC is a live bet against your own data); reallocate to `analyst` and lower gross — one-line `DEFAULT_WEIGHTS` change, defensible today.
2. Parameterize `compute_walk_forward_ic` with per-signal `eval_horizon_days`; stop judging factor/supply_chain/insider on 5d. Fixes the measurement layer everything else inherits.
3. Add a `coverage` field to RatingCard exposing which signals fired and the effective post-renormalization weight vector — kills silent off-panel/failure weight mutation.
4. Demote `adaptive_weights` to advisory; if/when wired, consume as shrinkage blend `0.5*default + 0.5*adaptive` with caps/floors, never raw — robustness against N≈16.
5. Stop feeding ~0.5 confidence into Kelly; split confidence (UI honesty) from sizing (derive from agreement + decile-spread).
6. Add decile top-minus-bottom spread as a co-objective alongside rank IC — it matches what a 5-tier rater actually does.
7. Replace the single universe parquet with a dated point-in-time membership table; unify live and backtest membership to kill survivorship asymmetry.
8. Harden cron fan-out (retry/backoff, cache last-good z with staleness flag) so the ~6% transient failures stop silently mutating composites.

## VERDICT
Solid, well-tested plumbing wrapped around a measurement-and-weighting core that is currently mismeasuring its best signals and over-weighting its worst — structurally healthy, evidentially mis-calibrated; fix the horizon and the weight wire before anything else.