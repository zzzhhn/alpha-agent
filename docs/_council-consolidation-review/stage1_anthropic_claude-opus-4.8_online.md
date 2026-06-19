This is a strong, self-aware brief. The fact that you've already done the "grounded read" distinguishing real fragmentation (registration spread) from imagined duplication (the factor/evolution/fusion layering is fine) means you've cleared the usual first hurdle. So I'll skip the easy wins and go adversarial on the parts where you're at risk of fooling yourself.

---

## PROPOSAL 1 — Signal-registry consolidation

**Is it sound? Yes, and it's the lowest-risk item here.** Ten hand-maintained registration sites for one signal is a defect, lists already drift in prod, and a central `SignalMeta` tuple with derived views is the textbook fix. The snapshot+drift test design is exactly right — you're asserting zero behavior change, which is the only way to do this kind of refactor safely.

**Strongest objection: you've identified the wrong axis of the problem.** The pain isn't "there is no central object" — it's "metadata that belongs next to code lives far from it." A central tuple *re-centralizes* and you'll still edit one file per signal add (just one instead of ten). That's a 10x win, but the decorator/self-registration question you raise is the better instinct. **The honest answer: do the central registry anyway, not the decorator — for THIS system.** Reasons:

- **Decorator self-registration requires eager import of every signal module to populate the registry.** That is precisely the import-time cost trap you flag, and it bites hardest in `fast_intraday` cron cold-starts on Vercel. A decorator registry is only populated after the module is imported; so either you import-all-at-startup (slow cold start, pulls pandas/numpy/sklearn graphs for signals a given cron doesn't use) or you have a half-populated registry depending on import order (a correctness landmine).
- **A static tuple is introspectable without executing signal code.** `DEFAULT_WEIGHTS`, `_CORE_SIGNALS`, `_TIERS`, the health endpoint, and the frontend codegen all need *metadata*, not the compute kernels. Decoupling metadata from the heavy module is a feature, not a smell, on serverless.
- Decorators put metadata next to code but make the *full set* non-enumerable statically — bad for a system whose whole problem is "enumerate all signals consistently."

So: central registry. But preempt these concretely:

**Traps and preemptions:**
1. **Circular imports.** `registry.py` must import *nothing* from `fusion`, `weights`, `backtest`, or signal modules. It holds plain data (strings, ints, floats, the module path as a *string* `"alpha_agent.signals.rsrs"`, not the imported module). Consumers import the registry, never the reverse. The module is resolved lazily via `importlib.import_module(meta.module)` only at the call site that actually needs to run the signal.
2. **Eager import in cron.** Do NOT have the registry import signal modules. `fast_intraday`'s `_ALL_MODULES` should be derived as `[m.module for m in REGISTRY]` (strings), and the cron lazily imports each as it runs it. Measure cold-start before/after; if the registry module itself accidentally pulls a heavy transitive import, you've regressed the thing you can least afford.
3. **Derived dicts must be functions or frozen at import, not mutable module-level dicts that something else patches.** Today some list is probably mutated somewhere (adaptive weights writing back?). Grep for in-place mutation of `DEFAULT_WEIGHTS` before you freeze it into a derivation, or the snapshot test passes and prod diverges at runtime.
4. **`cap` and `tier` semantics.** You're folding per-signal `cap` and `_TIERS` into one object. Confirm `_TIERS` is signal-partition metadata (which tier-bucket a signal feeds) and not the *output* tier mapping (`map_to_tier`'s BUY/OW/...). If those two "tier" concepts are conflated in the tuple field naming, you've built a new drift source. Name them unambiguously (`fusion_group` vs `rating_tier`).

**Frontend codegen vs runtime fetch:** Codegen, but only because you already have the `openapi->api-types.gen.ts` pattern — consistency with an existing, trusted mechanism beats introducing a second paradigm. The real argument for codegen over runtime fetch: the frontend mirrors (`signal-labels.ts`, `signal-horizons.ts`) are used at *build/render* time and a runtime fetch introduces a loading state + a failure mode (registry endpoint down → frontend shows wrong/empty labels) for data that changes maybe monthly. Build-time generation makes drift a *CI failure*, not a *silent prod inconsistency*. That's the whole point of this proposal. Wire the drift test so the frontend `.gen.ts` being stale fails CI exactly like `api-types.gen.ts` does.

**Dead-code deletion (Phase 3, llm/_legacy): under-valued, do it FIRST, not last.** Deleting dead code before refactoring means you don't waste effort wiring legacy paths into the registry or writing snapshot tests that pin behavior you're about to delete. Sequence: (1) delete `_legacy`, (2) build registry, (3) derive lists, (4) codegen frontend. You have it backwards.

**Over-engineering check:** The registry itself is right-sized. The risk of over-engineering is in the `SignalMeta` schema — don't add fields speculatively (`enabled`, `version`, `data_source`, `decay`) "while you're in there." Add exactly the 9 fields that replace existing hardcoded values. Every field is a new thing the snapshot test must pin and a new drift vector.

---

## PROPOSAL 2 — L2 forward paper-trading

**Is it the right next step? Partially — and this is where you're most at risk of self-deception.** L2 answers a question IC genuinely can't ("does the *tiering + sizing + rebalance policy* compound into equity"), and forward, look-ahead-free tracking is the gold standard for not fooling yourself. **But the strongest objection is brutal: at IC ~0.04–0.09 and confidence structurally ~50%, a single-user forward paper portfolio will not produce a statistically distinguishable signal from noise for years.**

Run the math on yourself before you build the dashboard:
- Rank-IC ≈ 0.05 implies a per-name, per-period information coefficient that translates (via roughly `IR ≈ IC × sqrt(breadth)`) into a usable information ratio only with breadth. With ~550 names and, say, weekly rebalance, breadth per year is order 550×50 ≈ 27,500 *if* signals were independent across names and time — they are emphatically not (factor exposure dominates, names are cross-correlated, signal autocorrelates week to week). Effective breadth is a small fraction of that.
- A top-N long-short basket of N=10–25 throws away most of the breadth that makes IC≈0.05 exploitable. **The IC lives in the cross-sectional ranking of all 550 names; concentrating into a 20-name basket converts a weak-but-broad edge into a high-variance bet.** This is the central tension: the thing that makes your edge real (breadth) is the thing a top-N basket discards.
- Forward, you'll have ~250 trading days/year = a handful of independent rebalance observations at weekly cadence. The equity curve's confidence interval will be enormous. You will not be able to reject "this is SPY + noise" for a long time, and your **one user will over-update on the first 6 months of curve** — the exact self-deception L2 was supposed to prevent.

**So: build L2, but as a measurement instrument, not a verdict machine — and decide the honest test BEFORE seeing results.** Pre-register the success criterion (t-stat on daily long-short return, target threshold, minimum sample) so you can't move the goalposts.

**Minimal correct design (specific enough to build):**

- **Picks: point-in-time only.** Persist each day's tier output to an immutable, append-only table keyed by `(date, ticker, tier, composite, coverage)` *as emitted by that day's cron*, never recomputed. The cardinal sin is regenerating "what the model would have said" with today's code/data — that re-introduces look-ahead and survivorship through the back door. If you don't already snapshot daily outputs immutably, **that table is the actual L2 prerequisite** and most of the value.
- **Weighting: do NOT use top-N equal-weight as your primary test.** Run a **rank-based, dollar-neutral, beta-hedged cross-sectional portfolio** as the primary (weight ∝ demeaned composite rank across all covered names, capped per name, then beta-neutralized vs SPY). This uses the breadth your IC actually has. Keep top-N as a *secondary, illustrative* book because it's intuitive to the user — but label it as the high-variance one. This directly answers your question: the most honest test is **broad rank-weighted, not concentrated top-N**.
- **Costs: model them as a hurdle you must clear, not an afterthought.** Free-data universe, so assume retail-ish: ~5–10 bps per side spread+slippage for S&P 500 names, more for the tail. At weekly rebalance with moderate turnover, costs of 20–60 bps/year are plausible and your gross edge from IC≈0.05 may be the same order of magnitude. **Show gross AND net side by side; if net ≈ benchmark, that IS the finding.**
- **Rebalance cadence: weekly, with a no-trade band tied to your existing hysteresis.** Daily rebalance will be eaten alive by costs at this IC; monthly throws away signal decay info (your horizons are 5–20d). Weekly with the hysteresis band suppressing churn is the honest middle. Tie turnover directly to the tier hysteresis you already have so the paper book and the live tiering are the same policy.
- **Position sizing: volatility-scaled or capped equal-risk, not equal-dollar.** Equal-dollar lets a few high-vol names dominate P&L and masks whether the *ranking* worked. Equal-risk (inverse-vol weight within the rank scheme) isolates the signal.
- **Survivorship / delisting / dead feed:** This is where paper portfolios lie most. yfinance silently drops/halts tickers; a name that goes to zero or gets acquired must be marked as a realized loss/event, not silently dropped (dropping = the survivorship lie that fabricates returns). Concretely: (1) on a delisting, force-liquidate the position at the last valid price and book it; (2) on a stale/NaN feed for a held name, carry last price for ≤3 days then force-mark and flag; (3) reconcile your held universe against the index membership *as of each date* — never use today's S&P 500 list to backfill, or you bake in survivorship.
- **Benchmark: SPY total return (with dividends), beta-matched.** Comparing a beta-hedged dollar-neutral book to long-only SPY is apples-to-oranges; report long-short vs cash/zero AND a long-only-top-decile vs SPY-TR. Pick the benchmark that matches each book's beta.

**Classic ways the paper portfolio lies, and preemptions:**
1. **Recomputing historical picks with current code** → immutable daily snapshot table.
2. **Survivorship via today's universe** → point-in-time membership.
3. **Marking to a price the model "saw" before it was tradable** (e.g., using the close that informed the signal as the entry) → enter at *next* available price after signal time.
4. **Zero/under-modeled costs** → explicit per-side hurdle, gross+net.
5. **Dividend/corporate-action blindness** → use adjusted-close consistently for both portfolio and benchmark, or neither.
6. **Cherry-picking the start date / N / rebalance after seeing curves** → pre-register.
7. **Over-updating on small samples** → display the confidence band and required sample-to-significance *on the dashboard itself*, next to the curve.

**Is L2 a distraction from fixing the signals?** It's a distraction *if you build the long-short top-N book and treat the curve as truth*. It's not a distraction if it becomes the **immutable point-in-time output ledger** — because that ledger is also what you need to (a) validate IC honestly going forward, (b) detect signal drift, and (c) eventually feed L3. Frame L2 as "build the forward truth-ledger; the portfolio is a view on it."

---

## METHODOLOGY gut-check

**Blunt verdict: the machinery is over-built relative to the edge, and the over-build is concentrated in the discovery/proposal layer while the trust layer is under-built.**

- **The evolution/LLM-factor-proposer + seccomp sandbox is the most expensive subsystem and the least justified at this edge.** Generating new candidate factors via LLM and config-knob search, then sandboxing arbitrary operator code, is serious engineering for a system whose best signal is IC≈0.087 and whose newest validated addition (RSRS) is IC≈0.043 with a known transfer failure (A-share M=600 didn't carry). **Searching for more weak, correlated signals has steeply diminishing returns** — the binding constraint isn't "not enough signals," it's "weak edge + no honest forward verification + inert weighting." The sandbox especially: in a single-user, research-only system, the threat model that justifies seccomp hardening (running untrusted code) is largely self-inflicted by choosing to run LLM-proposed code at all.

- **The adaptive-weights subsystem being INERT is the screaming finding.** You built an EWMA-ICIR adaptive weighting system, it computes weights into a table, and live crons ignore it in favor of hand-set weights. That's either (a) a half-finished high-value feature, or (b) an implicit admission that you don't trust the adaptive output enough to ship it. Either way it's the cheapest high-leverage move: **either wire it in behind a guardrail (shrink adaptive toward the static prior, cap per-signal weight moves, require minimum IC sample) or delete it.** A computed-but-ignored subsystem is pure liability — it costs maintenance, implies a capability you don't have, and erodes the one user's trust when they discover the "adaptive" weights do nothing.

- **Dropping low-IC signals: probably yes, but for the right reason.** Don't drop on IC magnitude alone — a low-IC, *decorrelated* signal (RSRS's whole thesis) adds to the portfolio even if its standalone IC is small. Drop signals that are *both* low-IC *and* correlated to the factor signal (redundant) *or* that fail to transfer/validate. Run a quick correlation matrix of signal z-scores; the ones clustered with `factor` and below ~0.03 IC are deadweight. The political_impact/geopolitical_impact/supply_chain signals are the prime suspects for low-IC-and-flaky-on-free-data — interrogate those first.

**Where effort is misallocated:**
- *Over-invested:* LLM factor proposer + sandbox, factor evolution search.
- *Under-invested:* forward output ledger (the L2 prerequisite), wiring or killing adaptive weights, honest cost/turnover accounting, and confidence calibration *that means something* (a "structurally ~50%" hit-rate calibrated to 50% is telling you the directional confidence carries little information — that's worth confronting, not displaying).

---

## RECOMMENDATIONS (ranked by leverage for THIS context)

1. **Build the immutable point-in-time daily output ledger first** — append-only `(date, ticker, tier, composite, coverage)`; it's the prerequisite for honest L2 *and* honest forward IC, and the single most trust-building artifact.
2. **Resolve the inert adaptive-weights subsystem now**: either wire it in with guardrails (shrink-to-prior, capped weight deltas, min-sample gate) or delete it — no computed-but-ignored systems.
3. **Do the registry consolidation** (delete `_legacy` first → central static tuple of metadata-only → derive all lists → codegen frontend like `api-types.gen.ts`), with circular-import and cron cold-start preemptions above.
4. **Build L2 as a rank-weighted, dollar-neutral, beta-hedged, cost-net book** on top of the ledger; pre-register the success threshold and show the confidence band on the dashboard.
5. **Prune signals on (low-IC AND correlated/non-transferring)**, not magnitude alone; political/geopolitical/supply_chain first.
6. **Freeze or shelve the LLM factor proposer + sandbox** until L2 demonstrates a forward edge worth expanding the signal set for.

## VERDICT

Right direction overall, but the highest-leverage move is neither proposal as scoped — **build the immutable point-in-time output ledger first (it's L2's real prerequisite and your only honest forward-verification substrate), then decide adaptive-weights live-or-die; the registry is correct but secondary, and the LLM/sandbox machinery should freeze until L2 shows an edge.**