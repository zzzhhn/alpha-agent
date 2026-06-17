### Deep Critique of alpha-agent Architecture

#### 1. **Dead Adaptive Weight Subsystem (weight_layer/adaptive_weights.py)**
   - **Why it matters**: The entire adaptive weight engine is inert - live crons ignore `signal_weight_current` and use statically hardcoded `DEFAULT_WEIGHTS`. This creates dangerous misalignment: factor/technicals have negative 5d IC but retain 50% weight allocation, while the adaptive system (if used) would zero them. The system is blind to signal decay.
   - **Concrete risk**: Research-grade signals are actively harmful at current weights (observed -0.09 IC for technicals), yet users receive BUY/SELL recommendations from corrupted composites. The subsystem's shadow existence creates false operational confidence.
   - **Optimization**: Immediately wire `slow_daily` cron to use `adaptive_weights.apply_adaptive_weights()` output with circuit breakers:
     ```python
     weights = load_adaptive_weights() if adaptive_enabled else DEFAULT_WEIGHTS
     if (np.abs(np.array(list(weights.values()))).sum() < 0.3):  # sanity check
         weights = DEFAULT_WEIGHTS  # fallback to static
     ```
     **Trade-off**: Adaptive weights may amplify noise in short IC windows, but inaction guarantees continued misweighting. Add a 0.05 weight floor to prevent total signal dropout.

#### 2. **Horizon Mismatch in Validation (backtest_layer/walk_forward_ic.py)**
   - **Why it matters**: Validating all signals at 5d horizon ignores fundamental design:
     - Factor signals typically target 3-12 month horizons (per [github.com/jasmehar-k/pelican](https://github.com/jasmehar-k/pelican))
     - Supply-chain signals operate on quarterly cadence
     - Premarket signals decay intraday
   - **Edge cost**: The observed negative IC for factor/technicals likely stems from horizon mismatch, not true signal failure. This causes valid alpha to be misclassified as junk while short-term noise (analyst) gets overweighted.
   - **Optimization**: Implement signal-specific horizons in `compute_walk_forward_ic()`:
     ```python
     HORIZON_MAP = {
         "factor": "21d",  # 1mo hold
         "supply_chain": "63d",  # quarterly
         "premarket": "1d",
         ... 
     }
     ```
     **Trade-off**: Requires maintaining signal metadata but prevents horizon contamination. Use [github.com/HazelnutHui](https://github.com/HazelnutHui) validation framework for regime-specific IC.

#### 3. **Static Universe Survivorship Bias (universe/SP500_UNIVERSE.parquet)**
   - **Why it matters**: Static parquet ignores index recompositions (e.g., VRT addition). Off-panel tickers silently lose factor signals via KeyError, creating selection bias. Backtests become inflated by survivorship (dead tickers excluded).
   - **Risk**: Live ratings for new additions use partial signals, while historical simulations overstate returns by 50-150bps (per [github.com/amit943c](https://github.com/amit943c)).
   - **Optimization**: Migrate to point-in-time universe service:
     ```python
     # In universe_builder.py
     def get_universe(as_of: date) -> List[Ticker]:
         return db.query("SELECT ticker FROM universe_history WHERE %s BETWEEN start AND end", as_of)
     ```
     **Trade-off**: Adds complexity but enables accurate backtesting and eliminates off-panel errors. Start with monthly S&P history from Compustat.

---

### Misprioritized Efforts
- **Low-value**: BYOK LLM key handling (edge case) while core weight system is dead. Supply-chain integration without PIT history (unbacktestable).
- **High-value missing**: 
  - Risk decomposition ([github.com/jasmehar-k/pelican](https://github.com/jasmehar-k/pelican) QP optimization)
  - Transaction cost modeling (Almgren-Chriss impact)
  - Purged cross-validation for weight tuning ([github.com/amit943c](https://github.com/amit943c))

---

### Methodology Questions
1. **5d Rank IC objective**: Wrong for non-intraday signals. Use horizon-mapped IC or Sharpe of L/S portfolios.
2. **Factor horizon mismatch**: Likely - factor z-scores built for medium-term but evaluated at 5d. Recalibrate or retarget.
3. **Adaptive subsystem**: Worth wiring immediately with two fixes: a) Horizon-aligned IC b) 0.05 weight floor.
4. **50% confidence**: Useless as calibrated. Replace with signal agreement (1/(1+var(z))) or drop until hit rate >55%.

---

### OPTIMIZATIONS 
1. **Wire adaptive weights** with circuit breakers and 0.05 floor (weight_layer)  
2. **Implement signal-specific horizons** in IC backtests (backtest_layer)  
3. **Migrate to point-in-time universe** (universe_builder.py)  
4. **Drop 5d IC as universal metric** - adopt signal-specific validation  
5. **Cache external API responses** in Postgres to reduce cron failures  
6. **Deprecate confidence metric** until statistically meaningful  

### VERDICT  
**Architectural triage required** - core subsystems (weighting/universe) misaligned with research goals, but salvageable via focused fixes.