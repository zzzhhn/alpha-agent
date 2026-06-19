Here is the adversarial, architectural review. 

### PROPOSAL 1: Signal-Registry Consolidation

**Is the proposal sound? Strongest objection:**
The move to a single source of truth is mandatory, but your proposed implementation (a central tuple of metadata) has a massive serverless trap. The strongest objection is **import-time explosion**. If your registry imports all 13 signal modules (and their heavy dependencies like pandas, scipy, sklearn, LLM libs) just to read metadata, you will destroy your Vercel/FastAPI cold-start times. Every cron execution and API call will load the entire universe.

**The better / minimal / less-self-deceiving version:**
Do NOT use decorator-based self-registration. Decorators require eagerly importing the universe to build the list, scattering truth across 13 files. Keep your central tuple, but use **lazy loading via string paths**. 
`SignalMeta(name="rsrs", module_path="alpha_agent.signals.rsrs", weight=1.0, ...)`
The registry must be a pure-Python file with zero external imports—no pandas, no fusion logic. Engine components read the tuple and `importlib.import_module(meta.module_path)` *only* when executing that specific signal.

**Concrete traps and preemptions:**
*   **Trap:** Circular imports derived from shared constants.
    *   *Preemption:* Isolate the registry in a leaf node (`alpha_agent.signals.registry`). It imports nothing. Everything imports it.
*   **Trap:** Runtime frontend fetching (`/api/_signal_registry`). Adds unnecessary network latency to UI load and sacrifices static typing.
    *   *Preemption:* Pre-build codegen. Write a 10-line Python script that imports the registry and dumps a TypeScript `signal-labels.gen.ts` file. Run it in your `npm run build` hook.
*   **Trap:** Undervaluing dead-code deletion.
    *   *Preemption:* You are under-valuing it. Delete `llm/_legacy` in the same PR. Dead code in quantitative systems inevitably gets accidentally resurrected or imported during refactors, causing phantom behaviors. Burn it.

---

### PROPOSAL 2: L2 Forward Paper-Trading

**Is L2 the right next step?**
Yes. Your backtests (IC engine) measure predictive correlation; L2 measures execution reality. Without L2, you are playing a video game. However, your longest-running trap will be fooling yourself with execution timing. 

**Minimal correct design & Preemptions:**
*   **Execution Timing (The Biggest Lie):** Free data (yfinance) is EOD or delayed. If you run your cron after hours to get today's close, you *cannot* transact at today's close. 
    *   *Preemption:* **Next-Day Open (NDO) execution**. If signal generates on Tuesday evening, entry price is Wednesday's Open.
*   **Costs:** ICs of 0.04–0.09 are too weak to survive high turnover.
    *   *Preemption:* Apply a brutal **10 bps (0.10%) one-way penalty** (fees + slippage + market impact) on every trade.
*   **Portfolio Structure (N & Rebalance):** A purely daily-rebalanced top-N portfolio on 0.04 IC will bleed to death by a thousand paper cuts (turnover costs).
    *   *Preemption:* Weekly rebalance, Equal Weight tracking. Top 20 Long, Bottom 20 Short (or just Top 50 Long vs SPY for simplicity). Implement a turnover buffer (e.g., if a stock drops from #20 to #22, do not sell it until it drops below #30) to slash transaction costs.
*   **Survivorship & Dead Feeds:** S&P 500 constituents change. Yahoo Finance data mutates historically (splits, delayed dividend adjustments).
    *   *Preemption:* Write the L2 engine as an append-only transaction ledger. Never historically recalculate entry prices. If a ticker stops pricing, force-liquidate at the last known close minus a 5% penalty to simulate delisting/illiquidity.

**Will it clear costs?**
With ~50% directional accuracy and 0.05 IC, a daily rebalanced long-short basket will almost certainly lose money after 10bps slippage. To extract juice from weak, slow factors, you must widen the holding period (weeks, not days) and minimize turnover. 

---

### METHODOLOGY Gut-Check

**Is it over-built?**
Brutally over-built. For a free-data, S&P 500 universe engine, you have constructed an institutional framework for retail signal-to-noise ratios. You hold yfinance data but are wielding LLM-based factor sandboxes and EWMA-ICIR adaptive weights. Free data is inherently noisy, delayed, and survivorship-biased. Complex non-linear combinations (adaptive weights, LLM evolutionary code generation) on noisy inputs guarantee out-of-sample failure due to overfitting.

**Where is effort misallocated?**
*   **Low Value:** The LLM factor-proposer, "evolution", and adaptive weights. The adaptive module is inert—leave it that way, then delete it. Equal-weighting (1/N) canonically outperforms complex dynamic weighting in high-noisy environments. Signals like "political_impact" and "calendar" are almost certainly noise generators masquerading as alpha.
*   **High Value Missing:** Corporate action handling, rigorous survivorship mapping, and true execution-lag mechanics.

**The single highest-leverage move for this context:**
Stop expanding the signal count and stop searching for new exotic factors. The highest leverage move is to deploy the **L2 Paper Trader with toxic execution assumptions (Next-Day Open, 10bps cost)** on a maximally stupid Equal-Weight basket of your 5 most mathematically sound, low-turnover factors (e.g., Value, Momentum, RSRS). You must prove to yourself that the core pipeline can defeat structural decay before you let an LLM write more factors.

---

### RECOMMENDATIONS

1.  **Deploy L2 paper-trading with Next-Day Open execution and 10 bps slippage**; this is the ultimate truth-teller for slow, weak-IC signals.
2.  **Permanently delete the adaptive-weights subsystem and LLM-evolution sandbox**; equal-weight your top signals to prevent overfitting to noisy free data.
3.  **Implement the Registry via lazy-load string paths**; hardcode the metadata, freeze the Vercel cold-start times, and decouple the modules.
4.  **Shift frontend signal syncing to build-time codegen**; keep the runtime boundary clean and strict.
5.  **Cull the bottom 50% of your current signals**; drop unstructured text/news/political inputs and keep only mathematically verifiable, low-turnover time-series factors.

### VERDICT
The core pipeline architecture (signals -> fusion -> tier mapping -> forward walk IC) is highly competent, but the methodology is drowning in complexity that outstrips its data grade; the single highest-leverage move is to halt signal discovery and deploy an L2 forward-tracker with punitive transaction costs to find out if the foundational alpha is real.