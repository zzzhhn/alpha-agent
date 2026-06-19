Here is the cross-review synthesis. 

### 1. Where do MULTIPLE reviews converge (Highest-Confidence Conclusions)?

*   **The central registry must be a data-only tuple using string paths.** Reviews A, B, and C agree completely: in a serverless/cron environment, decorators require eager module imports. Eager imports of heavy ML/pandas signal libraries will explode cold-start times. The registry must use lazy-loading via `importlib`. 
*   **Frontend syncing must be build-time codegen.** Reviews A, B, C, and D unanimously agree you should not do runtime `/api/_signal_registry` fetches. Generate TypeScript files at build time to fail CI on drift and remove frontend network latency.
*   **The pipeline is brutally overbuilt for free S&P 500 data.** Reviews B, C, and D all converge on the fact that LLM factor generators, seccomp sandboxes, and adaptive EWMA-ICIR weights are institutional-grade traps applied to noisy, delayed, free retail data. 
*   **L2 requires Next-Day (Open/Close) execution and punitive costs.** Reviews A, B, and C agree that "same close" execution is a lie. L2 must force a 1-day lag and impose a flat ~10 bps transaction cost, because a 0.05 IC cannot survive daily turnover frictions.
*   **Point-in-time immutability.** A, B, and C agree the core of L2 is an immutable, append-only database table of what the engine predicted *on that day*, to structurally prevent look-ahead bias and retroactive bug fixes.

---

### 2. Which claims are wrong, overstated, or misread the brief?

**Review D is dangerously wrong across the board.** 
*   *Wrong on Decorators & Redis:* D recommends decorator self-registration backed by a Redis cache to solve cron latency. This is amateurish. It requires instantiating an external KV store to hold what should be static boilerplate, and the decorators still force eager-import cold-start bloat. 
*   *Wrong on Costs:* D recommends Almgren-Chriss nonlinear market impact models (`turnover^1.5`). You are a single retail user trading the S&P 500. Your $10k–$100k sizing has zero market impact on a $50B mega-cap. You face spread and slippage, not institutional volume impact.
*   *Wrong on Adaptive Weights:* D recommends "Activating" the EWMA-ICIR weights. Review C is right: dynamic factor timing is notoriously difficult even for AQR; applying it to weak signals on yfinance data guarantees out-of-sample overfitting.
*(Note: Review D also hallucinated GitHub repos like `jasmehar-k/pelican` to sound authoritative. Ignore it).*

**Review B is right on the math, but wrong on the L2 product.**
*   Review B insists the L2 portfolio must be a "broad rank-weighted, dollar-neutral, beta-hedged cross-sectional portfolio" to capture the IC breadth. While mathematically pure, *this is a single-user system*. A retail user cannot execute 500 simultaneous fractional long/short trades daily. Review A's "Long-only top N" is the right primary L2 strategy, because L2 must simulate what the user will *actually trade*, even if it implies higher variance.

**Review C is overstated on "Delistings."**
*   C proposes a "force liquidate minus 5% penalty" if a ticker stops pricing. With yfinance, tickers "stop pricing" constantly due to ticker symbol changes (e.g., FB -> META) or feed glitches. Blindly docking 5% for an API glitch is self-flagellation, not rigorous backtesting.

---

### 3. What did ALL reviews miss?

1. **The 'yfinance' historical survivorship paradox.** All reviews demand "point-in-time S&P 500 universe mapping" to bypass survivorship bias in L2. They forgot you use `yfinance`. Yahoo Finance actively deletes historical ticker data for acquired/bankrupt companies. You literally *cannot* retroactively simulate an accurate L2 prior to today because the dead-ticker prices no longer exist on the public endpoint. L2 is strictly a *forward-only* ledger from the day you deploy it. Expect zero historical utility.
2. **Next-Day Open (NDO) is fatal on free feeds.** Reviews C (and A partially) demand NDO execution. yfinance open prices are notoriously buggy, often delaying stock split adjustments to the open, or reporting NaN/stale opens until 10:00 AM EST. If you execute L2 at the open on yfinance, it will fill at garbage prices. You must use Next-Day Close (NDC) or a TWAP proxy.
3. **No one tested the transaction logic.** Everyone discussed the database schema and portfolio weights. No one recommended writing unit tests explicitly injecting a 2:1 stock split, a 10% dividend, or a zero-volume day to ensure the L2 accounting correctly handles corporate actions without fabricating paper P&L.

---

### 4. Recommendations Re-Ranked (Leverage x Confidence x Ease)

For this specific single-user, free-data context, here is the ruthlessly prioritized order of operations:

**1. Slay the "Overbuilt" Dragons (Highest Leverage, Easiest)**
Make the system fit the quality of the data. Delete `llm/_legacy`, turn off/delete the LLM seccomp sandbox, and delete the inert adaptive weight subsystem. Hardcode 1/N equal weighting for core signals. Stop overfitting to noisy data. 

**2. Deploy the "Lazy String" Registry + Frontend Codegen (High Confidence, Easy)**
Proceed with Proposal 1, strictly using a pure-Python, import-free static tuple `SignalMeta("rsrs", "alpha_agent.signals.rsrs")` to preserve FastApi/Vercel startup times. Build the TypeScript generator script into your CI/CD. 

**3. Purge Redundant Alt-Data Signals (Medium Leverage, Easy)**
Run a correlation matrix on your signal z-scores. Cull any signal (likely the political/news ones) that has an IC <0.04 AND is highly correlated with another factor. Keep independent signals (even if low IC) like RSRS. 

**4. Build the Forward L2 Ledger & Paper Portfolio (High Leverage, Harder)**
Implement Proposal 2 as a completely isolated module that reads the daily engine output.
*   **Ledger:** Append-only database snapshot of the engine outputs at close.
*   **Strategy:** Equal-weight Top 20 or 50. 
*   **Execution:** Next-Day Close (NDC). NDO is too risky on yfinance. 
*   **Costs:** Hard 10 bps penalty per side. 
*   **Horizon:** Test for 6 months forward. Do not attempt to backfill.