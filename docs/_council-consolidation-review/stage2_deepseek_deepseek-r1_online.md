### 1. Convergent Conclusions (Highest Confidence)
**Proposal 1 (Registry):**
- **Central data-only manifest is essential** (A, B, C, D agree). Solves metadata sprawl but must avoid eager imports.  
- **Frontend codegen > runtime fetch** (A, B, C). Static generation prevents version skew and loading failures.  
- **Dead-code deletion is critical and under-valued** (B, C). Delete `llm/_legacy` *before* refactoring to avoid resurrecting obsolete paths.  

**Proposal 2 (L2 Paper-Trading):**  
- **Point-in-time snapshots are non-negotiable** (A, B, C, D). Immutable decision records prevent lookahead bias.  
- **Weekly rebalance > daily** (A, B, C, D). Daily churn destroys weak IC edges via costs.  
- **10bps+ costs must be modeled** (A, B, C). Gross returns are deceptive; net returns after slippage are the truth.  
- **LLM/sandbox is overbuilt for free-data edge** (B, C, D). IC 0.04–0.09 can’t justify evolutionary complexity.  

**Methodology:**  
- **Adaptive weights are inert and must be resolved** (B, C, D). Wiring or deleting EWMA-ICIR is higher leverage than L2.  
- **Prune low-IC, correlated signals** (B, C, D). `political_impact`, `supply_chain`, and `RSRS` (IC 0.043) are noise.  

---

### 2. Wrong/Overstated Claims  
**Review A:**  
- **Overstated:** *"L2 is the more important trust-building step."*  
  - **Why:** B/C/D prove L2 is theater without resolving adaptive weights or signal pruning first. Weak ICs + costs = noise.  
- **Misread:** *"Decorators cause eager imports."*  
  - **Why:** D correctly notes decorators *can* work with lazy-load (though central tuple is safer for serverless).  

**Review B:**  
- **Overstated:** *"Rank-weighted L2 is more honest than top-N."*  
  - **Why:** Ignores that free-data universes lack borrow cost data, making dollar-neutral books unrealistic. Top-N is more feasible.  

**Review D:**  
- **Wrong:** *"Almgren-Chriss impact costs are needed."*  
  - **Why:** Overkill for free-data S&P 500. Linear 10bps suffices (C). Nonlinear models assume institutional liquidity.  
- **Misread:** *"Decorators solve core fragility."*  
  - **Why:** A/B/C show decorators *introduce* cold-start latency vs. static tuples.  

**Review C:**  
- **Overstated:** *"Beta-hedging isolates signal."*  
  - **Why:** Beta-neutrality requires high-frequency rebalancing – infeasible with weekly L2.  

---

### 3. What All Reviews Missed  
- **Free-data corporate action handling:** None addressed backfilling dead-ticker prices (e.g., Yahoo Finance’s patchy historical delistings).  
- **Hysteresis as turnover control:** All ignored existing tier-band logic (e.g., holding #22 until #30) to reduce churn.  
- **User psychology:** No review considered dashboard design to prevent over-updating on noisy L2 curves (e.g., confidence bands).  

---

### 4. Re-Ranked Recommendations  
*(Leverage × Confidence × Ease for single-user free-data)*  
1. **Delete LLM/sandbox & activate adaptive weights**  
   - Leverage: ⭐⭐⭐⭐⭐ (Drops dead code, resolves inert subsystem)  
   - Confidence: All agree (B/C/D strongest)  
   - Ease: ⭐⭐⭐ (Delete files; add EWMA guardrails)  
   - **Why:** Highest ROI. Adaptive weights are computed but unused; LLM adds zero edge.  

2. **Build point-in-time ledger (L2 prerequisite)**  
   - Leverage: ⭐⭐⭐⭐ (Foundation for all forward tests)  
   - Confidence: A/B/C/D converge  
   - Ease: ⭐⭐ (Requires immutable DB schema)  
   - **Why:** Enables honest L2 *and* IC validation.  

3. **Prune signals**  
   - Leverage: ⭐⭐⭐⭐ (Cuts noise; focuses on robust factors)  
   - Confidence: B/C/D agree  
   - Ease: ⭐⭐⭐ (Drop modules from registry)  
   - **Why:** `political_impact` and `RSRS` are free-data liabilities.  

4. **Registry consolidation**  
   - Leverage: ⭐⭐⭐ (Hygiene fix)  
   - Confidence: All agree  
   - Ease: ⭐⭐ (Refactor with lazy-load strings)  
   - **Why:** Solves drift but secondary to edge issues.  

5. **Deploy minimal L2**  
   - Leverage: ⭐⭐ (Truth-test but low signal)  
   - Confidence: All agree with caveats  
   - Ease: ⭐ (Complex accounting)  
   - **Why:** Weekly top-20 long-only, 10bps costs, next-day open.  

---

### Adversarial Summary  
- **Converged:** Kill LLM/sandbox, fix adaptive weights, prune signals, and use static registries with codegen. L2 requires point-in-time snapshots and weekly cadence.  
- **Diverged:** B over-indexed on rank-weighted L2; D hallucinated institutional cost models; A underplayed adaptive weights.  
- **Blind spot:** Corporate actions and hysteresis are critical for free-data L2 but ignored.  
- **Top lever:** **Delete LLM and wire adaptive weights** – it’s shameful to compute weights but not use them. Paper-trading weak signals is performance theater.