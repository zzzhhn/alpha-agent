### Cross-Review of Alpha-Agent Architecture Audits

#### 1. Convergent Findings (Highest-Confidence Issues)
Three issues appear across all audits with high confidence:

1. **Dead Adaptive Weight Subsystem**  
   - **Audits A/B/C**: All identify that `signal_weight_current` is ignored in live production (`fast_intraday`/`slow_daily`). Static `DEFAULT_WEIGHTS` persist despite IC evidence (e.g., technicals at -0.09 IC retain 0.20 weight).  
   - **Impact**: Live composites actively contradict research evidence, creating anti-alpha.  
   - **Evidence**: Factor/technicals show negative 5d IC but dominate composites (50% weight), while positive signals (analyst) are underweighted.

2. **Horizon Mismatch in Validation**  
   - **Audits A/B/C**: Universal criticism of using 5d rank IC to evaluate all signals (e.g., factor designed for 20-60d judged on 5d).  
   - **Impact**: Invalid signal evaluation distorts weight allocation (e.g., punishing valid medium-term signals).  
   - **Evidence**: Factor shows negative 5d IC but may be profitable at 20d/60d; premarket/news decay faster than 5d.

3. **Static Universe Survivorship Bias**  
   - **Audits A/B/C**: `SP500_UNIVERSE.parquet` lacks point-in-time membership. Off-panel tickers (e.g., VRT) lose factor signals silently.  
   - **Impact**: Backtests inflate performance (survivorship bias), live composites mutate unpredictably via renormalization.  
   - **Evidence**: Key errors drop factor for new additions, redistributing weight to noisy survivors.

#### 2. Overstated/Misread Findings
**Misread: "Wire Adaptive Weights Immediately" (Audit C)**  
- **Why wrong**: Audits A/B prove adaptive weights are statistically dangerous with current data. 5d IC over 4 months yields ~16 non-overlapping observations (N≈16) — too noisy for hard drops. Wiring raw adaptive weights would nuke factor on insufficient evidence.  
- **Corrective**: Audit B’s **shrinkage blend** (e.g., `0.5*static + 0.5*adaptive`) is safer.

**Overstated: "Splitting into 4 Horizon Sleeves" (Audit A)**  
- **Why overkill**: Adding 1d/5d/20d/60d composites creates product complexity without solving core measurement error. Audit B’s **per-signal horizons** in IC calculation (e.g., `factor.eval_horizon=63d`) is sufficient.  
- **Risk**: Tiered ratings would confuse users and increase backtest costs 4x.

**Misread: "Supply Chain Weight Must Be Zero" (All)**  
- **Why wrong**: Supply-chain is explicitly exploratory (0.05 weight). Killing it ignores its role as a research prototype.  
- **Corrective**: Label it "unvalidated" in cards but retain for forward testing.

#### 3. What All Audits Missed
**AST Deduplication for Factor Originality**  
- **Critical Gap**: None address [AST deduplication](https://coriva.eu.org/en/alphaagent-paper-review/), which boosts hit ratios by 81% by preventing factor homogenization.  
- **Impact**: Without this, alpha decay accelerates as generated factors converge to public signals.

**Cost-Ignorant Backtests**  
- **Missed Flaw**: All use naive 5d returns ignoring transaction costs. [Coriva notes](https://coriva.eu.org/en/alphaagent-paper-review/) backtests assume "0.05% + 0.15%" fees, ignoring slippage — unrealistic for 50-stock portfolios.

**Regime Adaptation**  
- **Omission**: No audit tests signal performance across volatility/market regimes. Factor IC may be negative only in low-volatility periods.

#### 4. Re-ranked Findings by (Impact × Confidence × Ease)
**Top 5 Fixes**:  
1. **Cut technicals weight to 0**  
   - *Why*: -0.09 IC is toxic. Immediate 1-line change (`DEFAULT_WEIGHTS`).  
   - *Impact*: Stops active harm. *Ease*: Trivial. *Confidence*: High (A/B/C).

2. **Add per-signal horizons to IC backtests**  
   - *Why*: Fixes core measurement error (e.g., factor judged at 63d).  
   - *Impact*: Prevents misdiagnosis of valid signals. *Ease*: Medium (add `eval_horizon` to signals).  
   - *Confidence*: High (A/B/C).

3. **Expose signal coverage in RatingCard**  
   - *Why*: Ends silent weight mutation when signals fail.  
   - *Impact*: Restores transparency. *Ease*: Low (add metadata field). *Confidence*: High (A/B).

4. **Wire adaptive weights via shrinkage blend**  
   - *Why*: `0.5*static + 0.5*adaptive` with floors (0.02) avoids noise amplification.  
   - *Impact*: Aligns live with research. *Ease*: Medium. *Confidence*: High (B).

5. **Migrate to point-in-time universe**  
   - *Why*: Kills survivorship bias. Start with monthly S&P history.  
   - *Impact*: Fixes backtest inflation. *Ease*: High (vendor data required). *Confidence*: High (A/B/C).

**Lower Priority**:  
- Kelly sizing redesign (confidence is broken, but sizing isn’t critical path).  
- BYOK LLM refactor (display-only signals aren’t alpha-critical).  
- Hysteresis tweaks (works adequately today).

---

### Adversarial Summary
**Convergence**: Audits A/B/C unanimously indict dead adaptive weights, horizon mismatch, and static universes — **high-confidence, high-impact flaws actively costing edge**.  
**Divergence**: Audit A overengineers with horizon sleeves; Audit C dangerously pushes raw adaptive wiring.  
**Blind Spot**: All miss **AST deduplication** — the core innovation from [AlphaAgent’s regularization framework](https://coriva.eu.org/en/alphaagent-paper-review/) that fights alpha decay.  
**Action**: Slash technicals weight *today*, fix horizon validation, then implement shrinkage-blended adaptive weights. Without AST checks, factor decay remains a looming threat.