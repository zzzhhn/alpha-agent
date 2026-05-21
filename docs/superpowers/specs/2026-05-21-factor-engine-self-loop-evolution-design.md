# Factor Engine Self-Loop Analysis + Evolution (Phase 1 + 2)

**Date:** 2026-05-21
**Status:** Design approved, pending spec review
**Scope:** Phase 1 (self-measurement + confidence calibration) and Phase 2 (adaptive weights + human-gated methodology tuning). Phase 3 (LLM factor invention) is explicitly deferred to a separate planning round.

---

## 1. Motivation

One-line vision: every day, analyze how the factor engine's own past predictions and confidence performed against realized trading outcomes over a recent window, then dynamically adjust its own logic to raise future accuracy and returns.

Grounding the codebase reframed the work. Most of the "measure then adapt weights" loop is already architected but dormant:

* `alpha_agent/backtest/ic_engine.py` is a walk-forward IC backtest engine plus a dynamic signal weight writer. It computes Spearman rank IC per signal across {30, 60, 90} day windows versus forward 5 day returns (strict walk-forward, no lookahead), then writes adaptive weights: if min(IC) below 0.02 the weight is zeroed (auto dropped), else weight equals mean(IC) times a volatility normalize factor. It writes both `signal_ic_history` and `signal_weight_current`.
* `alpha_agent/fusion/combine.py::load_weights()` already reads `signal_weight_current` and feeds those weights into the live fusion.
* `config_change_log` (migration V009) is an append-only audit and rollback substrate.
* `daily_signals_fast` / `daily_signals_slow` already store the per-ticker per-day prediction record (composite, rating, confidence, and the breakdown z-scores).

Two gaps block this loop from running:

1. The forward-return leg of `ic_engine` joins `minute_bars`, which is only a rolling 7 day cache, so the 30/60/90 day windows cannot be computed. There is no daily-close price history table. (This is the same blocker found during the P0-3 review remediation.)
2. The IC engine is never scheduled in production (no cron entry).

And one capability is entirely missing:

3. Confidence calibration. `compute_confidence()` derives a number from z-score dispersion, but nothing measures whether the stated confidence matches the realized hit-rate. That is the "compare against confidence" half of the vision.

This design activates the dormant loop, hardens it per quant best practice, and adds confidence calibration plus a human-gated methodology proposer.

---

## 2. Research basis

A research pass (karpathy/autoresearch plus adaptive-quant literature) produced the safety backbone for this design.

* **autoresearch lesson:** safety comes from a strict separation, the LLM (or search) proposes, a fixed objective metric selects, and the data layer is frozen (only config is mutable). Replicated here: statistics is the fitness judge and the daily weight/confidence adaptation, the human gates methodology changes, the data and label layers are frozen.
* **Financial caveat:** a single out-of-sample window is too noisy to be a fair fitness function. The loop will hill-climb into noise unless changes pass multi-path out-of-sample validation deflated for the number of trials.
* **Adaptive weighting:** raw mean-IC weighting (the current rule) chases noisy IC and whipsaws. EWMA-ICIR (exponentially decayed mean-IC over std-IC) rewards stable predictive power instead.
* **Confidence:** reliability diagrams, Brier score, and isotonic or Platt recalibration are the standard tools. This is meta-labeling-lite, it can suppress overconfidence, it cannot invent signal.
* **Where an LLM helps:** only the slow outer factor-invention loop (Phase 3, deferred). Never in the daily reweighting path, where simple statistics is safer, cheaper, and auditable.

Reference URLs are listed in section 12.

---

## 3. Autonomy model (tiered)

Decided during brainstorming:

* **Auto tier (low blast radius):** per-signal fusion weights and confidence calibration. Applied automatically within change caps, in shadow first, with auto-rollback on degradation.
* **Approve tier (high blast radius):** methodology changes (rating tier thresholds, the no-trade band, default factor horizon, signal inclusion/exclusion, GEX regime rules, the IC-drop threshold). Produced daily as proposals with evidence, applied only on one-click human approval. Nothing in this tier auto-applies.

---

## 4. Architecture and data flow

```
DAILY EVOLUTION CRON (post market close)
 1. MEASURE   for each as_of in rolling window: join the stored prediction
              (daily_signals.breakdown z + rating + confidence) with the
              realized forward return ->
                per-signal Spearman IC x {30/60/90}d    [ic_engine, exists]
                per-confidence-bucket hit-rate + Brier   [new: calibration]
 2. ADAPT     (auto, low blast radius)
              weights = EWMA-ICIR, capped per update, floored -> signal_weight_current
                applied in SHADOW first -> promote if OK -> auto-rollback on degrade
              confidence recalibration map (isotonic) -> new table
 3. PROPOSE   (queued, high blast radius)
              candidate threshold / horizon / signal-set / regime changes
                scored on purged walk-forward + Deflated Sharpe ->
                one-click proposals into config_change_log
 4. SURFACE   daily self-analysis report (IC trend, calibration curve,
              what auto-changed, pending proposals, rollback history)

LIVE PATH (structurally unchanged)
   fast_intraday -> signals -> combine.load_weights(signal_weight_current)
   -> composite -> rating, then apply the confidence recalibration map
```

---

## 5. Phase 1a: forward-return foundation

* New table `daily_prices(ticker, date, close)` holding roughly 3 years of daily closes for the universe.
* Backfill via the production backend, because production yfinance access works while the local IP rate-limits on `.info` and history (the same constraint hit during the company-profile work). A backfill script populates it, the existing daily cron keeps it current.
* Repoint the `ic_engine` forward-return leg from `minute_bars` to `daily_prices`. Forward 5 day return is `close[t+5] / close[t] - 1`. The signal-side z-history it needs already lives in `daily_signals_fast.breakdown`.
* Wire `ic_engine` into a post-close daily cron. Once running, `signal_ic_history` and `signal_weight_current` populate. As a side effect this also fixes the P0-3 "IC columns empty" symptom for real.

## 6. Phase 1b: hardened adaptive weights

* Replace the raw `mean(IC) * vol_normalize` rule with EWMA-ICIR: weight proportional to an exponentially decayed mean-IC divided by std-IC, with a slow decay so the weights track stable predictive power rather than last-window luck.
* Change cap: a weight moves at most a bounded fraction per update (target near 15 percent), preventing whipsaw and runaway drift.
* Diversification floor: a single bad window shrinks a signal toward a floor rather than to a hard zero. A hard drop only triggers after N consecutive bad windows.
* Shadow, promote, rollback: candidate weights are computed daily and recorded as shadow. They are promoted to the live `signal_weight_current` only if they do not degrade against the frozen baseline over a shadow window. If the live composite IC or hit-rate degrades, the change auto-reverts via `config_change_log`.

## 7. Phase 1c: confidence calibration

* Measure: bucket predictions by stated confidence, compute realized hit-rate and Brier per bucket, build a reliability curve. Working hit definition: sign(forward 5 day return) matches the rating's directional call (BUY and OW expect up, UW and SELL expect down, HOLD excluded). This definition is tunable.
* Recalibrate: fit isotonic regression mapping stated confidence to realized hit-rate over a rolling held-out window, store the map in a new `confidence_calibration` table.
* Apply: the live path passes `compute_confidence` through the recalibration map so displayed confidence approximates realized hit-rate. This suppresses overconfidence only, it does not create signal.

---

## 8. Phase 2: methodology proposer (approve tier)

**Tunable knobs (existing config only, no new logic invention):** rating tier thresholds and the no-trade band, default factor horizon (short 12d/60d versus long 252d/126d), signal inclusion or exclusion (retire a chronically zero-IC signal, or re-admit one), GEX regime rules, the IC-drop threshold and vol-normalize factors.

**Proposal generation (statistics, not LLM):** a daily job enumerates a small, bounded set of candidate config deltas via local search around the current config, for example "BUY threshold 1.5 to 1.4", "drop signal X whose 90 day IC is near zero", "switch the default horizon".

**Validation gate:** each candidate is re-run composite to rating to PnL on purged walk-forward out-of-sample windows, with a purge and embargo gap of at least the forward horizon so there is no label leakage, producing a distribution of Sharpe and IC across paths rather than one lucky window. A Deflated Sharpe step discounts the best candidate by the number of candidates tried (honest trial accounting). Only candidates that beat the current config on the out-of-sample distribution and survive deflation become proposals. A hard cap limits the number of proposals per day.

**Approval queue:** proposals are written to `config_change_log` as pending rows carrying the delta, the evidence (Sharpe distribution, IC, Deflated Sharpe, number of trials), and a one-line rationale. The user reviews them in the UI and approves (applies and journals for rollback) or rejects with one click. Nothing in this tier auto-applies.

**Validation rigor decision:** the pragmatic purged walk-forward plus Deflated-Sharpe-lite (trial-count deflation) is built first. Full combinatorial purged cross-validation (CPCV) is a later stretch, not part of this scope.

---

## 9. Self-analysis surface (UI)

A new Evolution panel (on `/methodology` or its own route) shows: daily per-signal IC trend (from `signal_ic_history`), the calibration reliability curve and Brier score, what auto-changed today (weight deltas and shadow status), pending methodology proposals with evidence and approve or reject controls, and rollback history (from `config_change_log`).

---

## 10. Data model

**New:**
* `daily_prices(ticker, date, close)`, primary key `(ticker, date)`.
* `confidence_calibration(as_of, isotonic_map JSONB, per-bucket hit-rate and Brier)`.
* Shadow weights: a `status` or `shadow` column added to `signal_weight_current` rather than a separate table.
* Methodology proposals: extend `config_change_log` with a `status` column (pending, approved, rejected) and an `evidence` JSONB column.

**Reused, now actually live:**
* `signal_ic_history` and `signal_weight_current` (migration V005).
* `config_change_log` (migration V009), carrying both proposals and the rollback journal.
* `daily_signals_fast` and `daily_signals_slow`, the prediction record.

---

## 11. Guardrails (non-negotiable)

* Out-of-sample only, with a purge and embargo gap of at least the forward horizon (no overlapping-label leakage).
* Change caps: weights move at most a bounded fraction per update, thresholds bounded.
* Shadow mode and auto-rollback for the auto tier, a human gate for the methodology tier.
* Deflated Sharpe trial accounting: count every candidate evaluated, deflate accordingly.
* Diversification floor: never let a single window hard-zero a signal.
* Frozen data and label layer: the loop tunes config only, never the data pipeline or the label definition.
* Regime sanity gate: do not reweight aggressively while the regime probability is transitioning.

---

## 12. Testing strategy

* **Unit:** EWMA-ICIR math, change-cap clamp, isotonic monotonicity, the Deflated Sharpe formula, purge and embargo correctness (inject overlapping labels and assert they are dropped).
* **Integration (synthetic panel):** a strong synthetic signal makes its weight rise, a noise signal shrinks toward the floor (not hard-zeroed from one window), over-confident and under-confident predictions are corrected by recalibration.
* **Safety:** shadow mode never mutates live before promotion, auto-rollback fires on injected degradation, a methodology proposal never auto-applies, the Deflated Sharpe step rejects a candidate that won only by trial count.
* **Real-shape probe:** a live smoke test against the actual `daily_prices` and `daily_signals` shapes, not only mocks (per the project SDK-boundary rule).

---

## 13. Out of scope (this round)

* Phase 3: LLM-driven factor invention (proposing brand-new factor expressions and hypotheses, backtesting, selecting winners into the Zoo). This is the autoresearch-inspired outer loop and gets its own design and plan.
* Full combinatorial purged cross-validation (CPCV). The pragmatic purged walk-forward plus Deflated-Sharpe-lite is sufficient for this round.

---

## 14. Research references

* autoresearch: https://github.com/karpathy/autoresearch
* Meta-labeling: https://en.wikipedia.org/wiki/Meta-Labeling
* Walk-forward optimization: https://blog.quantinsti.com/walk-forward-optimization-introduction/
* CPCV, Deflated Sharpe, purging: https://en.wikipedia.org/wiki/Purged_cross-validation , https://www.mlfinlab.com/en/latest/cross_validation/cpcv.html
* Brier score and reliability diagrams: https://en.wikipedia.org/wiki/Brier_score
* Regime-switching HMM ensembles: https://www.quantstart.com/articles/hidden-markov-models-for-regime-detection-using-r/
* LLM factor discovery (deferred Phase 3 reference): https://github.com/microsoft/RD-Agent
* Existing project KB: `~/.claude/projects/-Users-a22309-claude-project/memory/quant_domain_knowledge.md`
