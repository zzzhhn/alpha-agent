# Cross-Review of Alpha-Agent Audits

## 1) Convergent findings (highest confidence)

All three audits independently land on the same three structural issues. That triangulation makes them the highest-confidence problems in the system.

**C1. The adaptive weight subsystem is severed from production; static weights are anti-correlated with realized IC.** All three flag that `fast_intraday`/`slow_daily` consume `DEFAULT_WEIGHTS` and never read `signal_weight_current`, leaving factor (0.30) and technicals (0.20) — 50% of gross weight — driving the composite despite negative 5d IC, while analyst (the only positive signal) sits at 0.10. This is unanimous and correct. It's also the only finding where all three propose materially different remedies (see §2), which matters for ranking.

**C2. The 5d rank-IC objective is horizon-incoherent with the signals it judges.** All three argue that scoring factor/supply_chain/insider on a fixed 5d forward return is a category error, and that the observed negative factor IC likely reflects wrong horizon rather than dead signal. Unanimous and correct.

**C3. The static universe parquet creates survivorship bias and a silent factor-drop hole.** All three flag the static `SP500_UNIVERSE`, off-panel `KeyError`, and the need for point-in-time membership. Unanimous and correct.

These three should be treated as established. The interesting work is in adjudicating *how* they're addressed, because the audits disagree sharply — and one of them is dangerously wrong.

## 2) Wrong, overstated, or misread findings

**Audit C's headline remedy is the most dangerous error in the set.** C recommends wiring `apply_adaptive_weights()` into the live cron **immediately**, with only a crude sanity check (`abs sum < 0.3 → fallback`) and a 0.05 floor. This directly contradicts C's *own* second finding. If the 5d objective is horizon-incoherent (C2, which C endorses), then the adaptive weights derived from that objective are themselves contaminated — they hard-dropped factor precisely *because* of the broken measurement. Wiring them live "immediately" operationalizes the measurement error C just warned about. Audits A and B both catch this: A insists on shadow-mode for 4–8 weeks; B quantifies *why* — the effective sample is tiny (overlapping 5d returns across a ~557-name panel over ~4 months yields roughly a dozen-odd non-overlapping observations), so zeroing factor on −0.013 IC is fitting to noise. **C's "wire it now" is the single worst recommendation across all three audits.** Its sanity check is also nearly useless: a degenerate all-weight-on-one-signal vector passes `abs sum < 0.3` trivially.

**Audit C is padded with irrelevant/unverifiable citations.** C cites several GitHub repos (pelican, HazelnutHui, amit943c) as authorities for horizon choices, survivorship magnitude ("50-150bps"), and validation frameworks. These are presented as evidence but are unverifiable hand-waves — the 50–150bps survivorship figure in particular is asserted with false precision and no derivation. Treat C's quantitative claims as unsupported.

**Audit C contradicts itself on the confidence metric.** In its methodology section C proposes replacing confidence with "signal agreement (1/(1+var(z)))" — but A explicitly and correctly demolishes that exact formula, noting low variance among weak/stale signals produces spuriously high agreement. C reaches for the broken metric as the fix.

**Overstatement (A and C): "factor/technicals are actively harmful / anti-aligned."** A says the live composite is "likely anti-aligned with the empirical 5d objective"; C says signals are "actively harmful." This overstates what the evidence supports. Negative *5d* IC on a signal designed for longer horizons does not establish that the signal harms the *composite* at the product's effective horizon — that's the very horizon-mismatch point all three otherwise make. B is the most disciplined here: it isolates technicals (−0.09, large and consistent) as defensibly cuttable today, while treating factor's −0.013 as too small/noisy to act on. B's narrower claim is the correct one; A and C over-extend the "anti-aligned" framing to factor where the magnitude doesn't justify it.

**Overstatement (A): the scope of the rewrite.** A's recommendation to split into four horizon sleeves, build four PIT tables, calibrate tiers from forward-return buckets, and add composite attribution is individually defensible but collectively a near-total re-architecture presented as remediation. Much of it is sound direction, but A under-weights that several pieces (e.g., factor/supply_chain IC validation at 60d) are *impossible* on current data depth — a point B makes explicitly and A largely glosses. Building horizon-specific *validation* for signals you cannot yet validate is partly theater.

**Misread (A): BYOK news as "structurally inconsistent."** A is directionally right that user-supplied read-time LLM output shouldn't feed shared backend picks. But A frames this as a current alpha contamination when news carries only 0.10 weight and the brief doesn't clearly establish that read-time BYOK output is what feeds the *backend* composite (vs. display-only persona explanations). A asserts the failure mode without confirming the wiring; it's a real risk to verify, not a confirmed flaw.

**Minor (B): the "N≈16" precision.** B's shrinkage logic is the best-reasoned remedy in the set, but the specific "~16 non-overlapping observations" is a back-of-envelope dressed as a figure. The *direction* (effective N is far below 8000 due to overlap and cross-sectional correlation) is correct and important; the exact number shouldn't be quoted as if derived.

## 3) What ALL THREE missed

- **No one questioned the reported ICs themselves for look-ahead/leakage in the IC computation.** All three accept factor −0.013, technicals −0.09, analyst +0.013 as ground truth and argue about how to *use* them. But B alone gestures at panel-composition leakage in the factor *scores*; none audited whether `compute_walk_forward_ic` itself is sound: are signal `as_of` timestamps strictly prior to the `LEAD(close,5)` window, or is there same-day overlap? If `as_of` and the forward-return start are misaligned, every IC in the brief — and thus every conclusion in all three audits — is built on sand. This should have been finding #1 before anyone reallocates a single weight.

- **Analyst's positive IC got almost no skeptical scrutiny as a reallocation *target*.** A asks the right diagnostic questions but B and C reflexively propose *moving weight to analyst* as the safe move. At +0.013/+0.026 over the same tiny effective N, analyst's positive IC is as statistically fragile as factor's negative one. Reallocating *toward* it is the same noise-fitting error in the opposite direction. None of the three flag that the "obvious" reallocation is symmetric to the mistake they're warning against.

- **Multiple-hypothesis / selection effects across 13 signals.** With 13 signals tested at one horizon, some will show significant IC by chance. No audit mentions multiple-comparison correction or that "analyst is the one positive signal" is exactly what you'd expect from noise across 13 candidates.

- **Cost, turnover, and capacity are nearly absent.** Only C mentions transaction costs (briefly, as a "missing piece"). None integrates turnover into the weight decision: a higher-IC signal that reshuffles the book daily can be worse net than a lower-IC stable one. For a *rating* product this is softer, but A's own decile/turnover suggestion never connects back to the weight remedy.

- **The dual API entrypoint and cron region issues are operational, but no one assessed correctness divergence risk concretely** — i.e., whether the two router paths can serve *different ratings* for the same ticker. A flags the drift; none tests whether it's already producing inconsistent output.

- **No one defined what the product's *actual* decision horizon is.** Everyone says "match signal horizon to evaluation horizon," but nobody asks: what horizon does the *user* hold? The right objective is anchored to user holding period, and that's never stated. All the horizon-sleeve machinery is unanchored without it.

## 4) Re-ranked union of real findings (impact × confidence × ease)

Ordered most-worth-doing first. Rationale in brackets.

1. **Validate the IC pipeline for timestamp alignment / look-ahead before acting on any IC number.** [Highest impact — every other finding depends on these ICs being real; high ease; missed by all three. Do this first or everything below is built on possibly-corrupt evidence.]

2. **Add a `coverage` field to the RatingCard exposing which signals fired and the effective post-renormalization weight vector.** [High impact (kills the silent weight-mutation correctness bug from C3), high confidence, very cheap — one field. B's framing. This is the highest-leverage low-cost move.]

3. **Parameterize `compute_walk_forward_ic` with per-signal `eval_horizon_days`.** [Fixes C2, the measurement layer everything inherits. Moderate ease. Caveat: accept that factor/supply_chain remain unvalidatable on current data depth — mark them "horizon-unvalidated" rather than pretend.]

4. **Cut technicals from 0.20** (reallocate to *lower gross/cash-neutral*, NOT reflexively to analyst). [B's defensible-today move. −0.09 is large and consistent enough to act on; one-line change. Deviation from B/C: do not pile the weight onto analyst — its positive IC is equally fragile.]

5. **Demote adaptive weights to advisory + shadow mode; if/when consumed, use a constrained shrinkage blend with floors/caps computed at native horizon — never raw, never "immediately."** [Resolves C1 correctly. Explicitly rejects Audit C's wire-it-now remedy. B's shrinkage + A's shadow window are the right synthesis.]

6. **Set supply_chain production weight to 0 (from 0.05) until PIT history and forward evidence exist.** [Cheap, removes an unvalidated/unbacktestable input. A's stricter "0" beats B's "keep at 0.05 labeled" — there's no forward evidence to justify any nonzero weight.]

7. **Replace the single universe parquet with a dated point-in-time membership table; unify live and backtest membership.** [Fixes C3's root cause. High impact but real backfill cost — lower than #1–4 on ease, which is why it ranks below the cheap transparency fix in #2.]

8. **Decouple confidence from Kelly sizing.** [Feeding ~0.5 directional confidence into Kelly is near-useless and sign-unstable near the boundary. Do NOT replace it with `1/(1+var(z))` per C — A correctly shows that's broken. Split UI-honesty confidence from sizing; derive sizing from a proper expected-return/risk model if at all.]

9. **Add decile top-minus-bottom spread as a co-objective alongside rank IC.** [B's point: it matches what a 5-tier rater actually does better than raw IC. Moderate ease, good impact.]

10. **Harden cron fan-out** (retry/backoff, cache last-good z with staleness flag) so ~6% transient failures stop silently mutating composites. [Feeds back into #2; moderate effort.]

11. **Unify `api/index.py` and `app.py` to one router path.** [Cheap hygiene; verify it isn't already serving divergent ratings — the unaudited risk.]

**Deferred (real but lower priority):** A's full four-sleeve re-architecture, calibrated tier thresholds from forward-return buckets, composite attribution reports. All sound in direction, but they're large builds that depend on #1, #3, and #7 being done first, and several can't be meaningfully validated on current data depth.

**Explicitly rejected:** wiring adaptive weights live now (C); reallocating cut weight onto analyst on faith (B/C); `1/(1+var(z))` as the confidence replacement (C); treating C's cited survivorship/horizon figures as evidence.

One-line verdict: all three correctly identify *what's* broken (weights, horizon, universe); B reasons best about *how cautiously* to fix it, A is most thorough but over-scopes, C is confidently wrong on the one action that could do real damage — and **all three skipped checking whether the ICs they're arguing over are even computed correctly.**