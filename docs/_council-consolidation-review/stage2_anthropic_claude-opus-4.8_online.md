# Cross-Review: Alpha-Agent Engine Changes

## 1. Where Multiple Reviews Converge (highest-confidence)

These are the conclusions with 3–4 independent votes. Treat them as decided.

**Registry: central static manifest, NOT decorator self-registration (A, B, C against D).** Three of four converge hard, with the *same mechanical reason*: decorators require eager import of every signal module to populate the registry, which destroys serverless cold-starts and pulls heavy transitive deps (pandas/scipy/sklearn) for signals a given cron doesn't use. D is the lone dissenter and is wrong on this point (see §2).

**Registry must be a data-only leaf module with string import paths, lazy-loaded via `importlib` (A, B, C, D — even D agrees on lazy-loading).** Unanimous on the mechanism: `module_path="alpha_agent.signals.rsrs"` as a string, resolved only at the call site that runs the signal. Registry imports *nothing* heavy; consumers import registry, never the reverse.

**Frontend via build-time codegen, not runtime fetch (A, B, C, D).** Unanimous. Shared reasoning: a runtime `/api/_signal_registry` fetch adds a loading state and a failure mode for data that changes monthly, and codegen makes drift a CI failure rather than a silent prod inconsistency — consistent with the existing `api-types.gen.ts` pattern.

**Delete `llm/_legacy` aggressively; reviews say it's *under-valued* (A, B, C).** B and C go further: delete it *first*, before the refactor, so you don't wire dead paths into the registry or pin them in snapshot tests.

**L2 execution timing must avoid same-close lookahead; fill on the next bar (A, B, C, D).** Unanimous that same-close execution is the cardinal lie. Note a real disagreement on *which* next bar (§2).

**Costs must be punitive and reported gross+net; ~5–20 bps/side (A, B, C, D).** Unanimous that weak IC (0.04–0.09) may not survive turnover, so costs are a hurdle to clear, not an afterthought.

**Weekly rebalance with a turnover/no-trade band, not daily (A, B, C; D implies via 21-day hold).** Daily rebalance on this IC "bleeds to death by a thousand paper cuts."

**Point-in-time / append-only snapshots; never recompute historical picks; never reconstruct universe from today's index (A, B, C, D).** Unanimous, and the strongest convergence in the entire review set.

**The LLM factor-proposer + evolution + sandbox is over-built for free-data S&P 500 signal-to-noise and should be frozen/shelved (B, C, D; A implies via "don't add more machinery").** Strong convergence.

**The inert adaptive-weights subsystem is the screaming finding — resolve it (B, C, D explicit; A implies via the WeightPolicy layering).** Note the sharp split on *direction* (§2).

---

## 2. Wrong, Overstated, or Misread Claims

**D: "static tuple is inferior to decorator-based self-registration."** Wrong, and self-contradicting. D simultaneously demands decorators *and* lazy-loading — but decorators populate the registry only *after* module import, so you cannot enumerate signals without importing them all. That is the exact cold-start trap A/B/C call out. D's own "lazy-load only metadata at startup" is impossible with decorators: the metadata *is* the side effect of importing the heavy module. Internally incoherent.

**D: citing a GitHub repo (`jasmehar-k/pelican`) and `Liu-Ming-Yu/alpha-forge` as authority for the `@register` pattern and `turnover^1.5` costs.** These read as fabricated or irrelevant citations dressed as precedent. Discard them; judge the patterns on merits, not on a repo name.

**D: "Cache REGISTRY in Redis after first load."** Over-engineered and backwards. The whole point (per A/B/C) is that the registry is *static data versioned with the app* — adding a network-backed cache for a frozen Python tuple introduces a failure mode and skew for zero benefit. This contradicts D's own "frontend should be codegen not runtime fetch" reasoning.

**D: "Backfill dead tickers via Yahoo Finance historical API or assume -100% return."** Misreads the brief. This is a *forward* paper-trading harness. You don't backfill survivorship — you snapshot universe membership going forward and hold positions until an explicit exit/corporate action (A and B get this right). Assuming -100% on any stale feed is *over*-punitive and fabricates losses just as silently dropping fabricates gains.

**D: "Drop signals with IC < 0.06 (e.g., RSRS, political_impact)." Pure-magnitude pruning is wrong, and B explains why.** A low-IC but *decorrelated* signal (RSRS's entire thesis) adds portfolio value even at IC 0.043. The correct cut is *low-IC AND correlated-to-factor* (redundant) OR *fails to transfer/validate*. D would delete the one signal whose stated reason for existing is decorrelation. C makes the same error listing RSRS as a "mathematically sound" keep in one place while the logic argues for decorrelation — be explicit: keep on decorrelation evidence, not vibes.

**D: "Activate adaptive weights immediately to replace static WeightPolicy" is overstated and dangerous.** C and B both note the opposite risk: complex dynamic weighting on noisy free data overfits, and 1/N canonically beats dynamic weighting in high-noise regimes. The inert subsystem is a finding to *resolve* (wire-behind-guardrails *or* delete), not a feature to flip on raw. B's framing is correct: shrink-to-prior, cap weight deltas, min-sample gate — or delete. "Activate immediately" skips every guardrail.

**C/D: "daily long-short will almost certainly lose money / lose money after 10bps."** Overstated as stated — it's presented as near-certain fact. The honest version is B's: at this IC you likely *cannot statistically distinguish from noise for a long time*. "Will lose money" and "is indistinguishable from SPY+noise" are different claims; the second is the defensible one.

**A: long-only top-N equal-weight as the *primary* test.** B's objection is the stronger one and A is partially misreading the leverage: the IC lives in the *cross-sectional ranking of all ~550 names*; concentrating into a 50–75 name long-only basket discards most of the breadth that makes a weak edge exploitable. A's L2-A is the right *user-facing* book but the wrong *primary measurement instrument*. B's rank-weighted, dollar-neutral, beta-hedged book is the correct primary. This is a real, substantive disagreement, and B wins on the math.

**B's breadth math is directionally right but numerically loose.** `IR ≈ IC × √breadth` with "breadth ≈ 27,500" then hand-waved down is fine as intuition, but presented with too much precision. The conclusion (effective breadth is a small fraction; concentrated baskets waste it) is correct; don't over-trust the specific numbers.

**C: "Next-Day Open (NDO) execution" as strictly correct.** A disagrees and A is more conservative/right for *this* stack: with yfinance daily data, next-day *open* prices are often unreliable, so signal-on-D-close → fill-on-D+1-*close* is harder to fool yourself with. NDO is defensible only if you can prove open-price reliability. Flag as unresolved; default to D+1 close for honesty, NDO only if open data is validated.

**D: Almgren-Chriss `turnover^1.5` impact for a single-user S&P 500 book.** Market-impact models are for size that moves the tape. A single retail user's notional has negligible impact on large caps; a flat per-side bps hurdle (A/B/C) is more honest than a nonlinear impact term that implies institutional size you don't have.

---

## 3. What ALL Reviews Missed

**Statistical power as a build-gate.** Only B raises sample-size/confidence-interval honesty, and even B treats it as a dashboard feature. Nobody states the corollary: **if a weekly-rebalance forward test on ~50 obs/year cannot reject "SPY+noise" for years, then L2 cannot be the thing that decides go/no-go on the engine in any reasonable timeframe.** That reframes the entire priority debate — L2's value is almost entirely the *ledger*, not the *verdict*. Every review ranks L2 highly as a truth-teller without confronting that its verdict arrives too late to be the decision instrument.

**The seccomp sandbox threat model is self-inflicted — but nobody asks why the LLM proposer exists at all.** B notes the threat model is self-inflicted, but no review questions the *premise*: in a single-user research engine, why is there a code-execution sandbox at all instead of LLM-proposes-config / human-approves-and-hand-codes? The cheapest fix isn't hardening or freezing the sandbox — it's removing the need for one.

**No review checks whether the existing daily cron already persists outputs.** B asserts the immutable ledger is "the real prerequisite" but nobody verifies whether the system *already* writes daily rating rows that could be made append-only with a constraint change vs. needing a net-new pipeline. The effort estimate for "build the ledger" swings 10x on this unexamined fact.

**Nobody addresses backtest↔L2 reconciliation.** You'll now have two truth sources: historical forward-walk IC and the forward L2 ledger. No review specifies that these must be reconciled (same universe, same point-in-time logic) or you'll get two conflicting "truths" and trust *decreases*.

**Confidence calibration finding is noted but not actioned.** B observes "structurally ~50%" hit-rate means directional confidence carries little information, but no review draws the operational conclusion: the calibration display is arguably *anti-trust* (it presents 50.8% as if it's information). Either fix what it measures or stop showing it as a confidence signal.

**Free-data adjusted-close instability over time.** C and D mention yfinance mutates historically (splits/dividends), but no review notes this *also corrupts the append-only ledger retroactively* — if you store marks using adjusted close and Yahoo re-adjusts, your "immutable" equity curve silently changes. The ledger must store *raw* prices + an adjustment factor snapshot, not adjusted close.

**Cron tier / `_TIERS` semantic ambiguity is flagged but no review demands an audit of current meaning.** A and B both warn the "tier" field is overloaded, but neither says: before migration, grep every use site and prove what `_TIERS` currently means in each, or the registry codifies an existing latent bug.

---

## 4. Re-Ranked Union of Real Recommendations

Scored by **leverage × confidence × ease** for a single-user, free-data context. I'm collapsing duplicate recommendations and dropping the rejected ones (decorators, Redis cache, Almgren-Chriss, activate-adaptive-raw, drop-RSRS-on-magnitude).

**Tier 1 — do now (high on all three axes)**

1. **Delete `llm/_legacy` and freeze the LLM proposer + sandbox.** Highest ease (deletion), high confidence (B/C/D converge), high leverage (removes the most expensive, least-justified subsystem and a self-inflicted threat model). Tag the repo first. Do this *before* the registry refactor so you don't pin dead behavior.

2. **Build the immutable, append-only point-in-time output ledger** — `(run_id, date, ticker, composite, tier, coverage, universe_membership, effective_weights)` storing *raw prices + adjustment-factor snapshot*. This is L2's real prerequisite *and* the substrate for honest forward IC. Leverage is maximal; ease depends on whether daily cron already writes rating rows (verify first — could be a constraint change, not a new pipeline).

3. **Registry consolidation: data-only leaf manifest, string import paths, derived lists, codegen frontend.** Confidence is unanimous; leverage is real (kills 10-site drift); ease is moderate. Preempt: separate `cron_group` / `rating_tier` / `ui_group` fields (no overloaded `tier`); audit current `_TIERS` meaning first; add the lazy-import regression test (`assert "yfinance" not in sys.modules` after importing registry); add zero-behavior-change snapshot + permanent invariant tests.

**Tier 2 — do after the ledger exists**

4. **Resolve adaptive weights: wire behind guardrails OR delete.** High leverage (computed-but-ignored = pure liability + erodes trust), high confidence on the *finding*. Ease is moderate and direction is contested — so make it a forced decision, not a default-on. Guardrails if kept: shrink-to-static-prior, cap per-signal weight deltas, min-IC-sample gate. If you can't commit to guardrails this cycle, delete it — an inert "adaptive" system is worse than none.

5. **Build L2 as a measurement instrument, primary = rank-weighted, dollar-neutral, beta-hedged, cost-net book; secondary = long-only top-N for user intuition.** Pre-register the success threshold and minimum sample *before seeing curves*. Display the confidence band on the dashboard. Execution: D+1 close (NDO only if you validate open-price reliability). Costs: 10 bps/side long-only, more for L/S. **Frame explicitly as the ledger's view, not a verdict** — and accept its verdict won't be statistically usable for a long time. Leverage is high but its *decision value* is deferred, which is why it ranks below the ledger that feeds it.

6. **Prune signals on (low-IC AND correlated-to-factor) OR (failed transfer/validation), never magnitude alone.** Run the signal z-score correlation matrix first. Prime suspects: political_impact, geopolitical_impact, supply_chain. Explicitly *keep* RSRS unless its decorrelation thesis fails empirically. Moderate leverage, high ease, high confidence on the *method*.

**Tier 3 — explicitly defer or reject**

7. **Reconcile backtest IC and L2 ledger to one point-in-time logic** (missed by all reviews) — schedule once L2 exists, or you manufacture two conflicting truths.

8. **Fix or remove the confidence-calibration display** — a 50.8% "confidence" presented as information is anti-trust. Low ease to fix properly; cheap to stop displaying.

9. **Regime-aware backtesting (D only).** Reject for now: adds model surface and overfitting risk on noisy free data before the foundational edge is even verified. Premature.

10. **Almgren-Chriss nonlinear costs (D).** Reject: implies institutional size you don't have. Flat per-side bps is more honest.

**One-line synthesis:** The two proposals are both correct and both secondary. The real first move is *delete the over-built discovery layer and build the append-only point-in-time ledger* — that single artifact is the prerequisite for honest L2, honest forward IC, and the adaptive-weights decision, and it's the only thing here that strictly increases truth rather than the appearance of it.