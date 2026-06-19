### Proposal 1: Signal-Registry Consolidation  
**Sound?** Partially. Centralizing metadata reduces drift, but a static tuple is inferior to **decorator-based self-registration** (like [`jasmehar-k/pelican`](https://github.com/jasmehar-k/pelican)'s `@register` pattern). Strongest objection: **It fails to solve the core fragility** – signals still require manual import in code, risking overlooked dependencies or init errors during cron jobs. Deriving weights/horizons from a central object risks import cycles if signals reference the registry.  
**Better version:**  
- Use **decorator self-registration** (`@signal_meta` in each signal module) populating a global `REGISTRY` dict.  
- **Prevent eager imports:** Lazy-load modules during cron via `importlib` (only load metadata at startup).  
- **Frontend:** Generate TS types via CLI script (run pre-build), not runtime fetches.  
- **Traps:**  
  1. Circular imports if signals import registry → Fix: Use absolute imports + standalone `registry.py` with no deps.  
  2. Cron latency → Fix: Cache `REGISTRY` in Redis after first load.  
  3. Dead-code deletion under-utilized → Require registry membership for backtest inclusion (auto-prune orphans).  

### Proposal 2: L2 Forward Paper-Trading  
**Sound?** No. IC alone is insufficient, but paper portfolios **lie by omission** without:  
- **Point-in-time survivorship:** Free data lacks delisted tickers. Strongest objection: **Ignoring dead tickers inflates returns** (e.g., -100% drops missing).  
- **Costs:** Ignoring nonlinear impact (Almgren-Chriss: `turnover^1.5`) overstates profits, especially for small caps.  
**Minimal honest design:**  
1. **Universe:** Query `daily_prices` for existence on `rebalance_date` (point-in-time).  
2. **Portfolio:** Equal-weight long top 20 BUY/OW, short bottom 20 UW/SELL.  
3. **Costs:** 5bps spread + `0.1% * |turnover|^1.5` impact (per [`jasmehar-k/pelican`](https://github.com/jasmehar-k/pelican)).  
4. **Corporate actions:** Use yfinance-adjusted prices.  
5. **Benchmark:** SPY total return (reinvest dividends).  
6. **Output:** Report net Sharpe after costs vs. SPY.  
**Traps:**  
- Survivorship bias → Fix: Backfill dead tickers via Yahoo Finance historical API or assume -100% return.  
- Overfitting → Hold 21 days (signal horizon) to reduce turnover.  

### Methodology Gut-Check  
**Overbuilt?** Yes. Key issues:  
- **Low-edge signals:** Free-data ICs (0.04–0.09) imply most signals add noise. RSRS (IC 0.043) likely fails cost hurdle.  
- **Wasted complexity:** LLM factor proposer + sandbox is unjustified for free data (low signal-to-noise ratio). Adaptive weights inert = dead infrastructure.  
- **Missing leverage:** No regime testing (e.g., risk-on/off splits per [`Liu-Ming-Yu/alpha-forge`](https://github.com/Liu-Ming-Yu/alpha-forge)) or drawdown veto.  
**Highest-leverage move:** **Fix adaptive weights** (activate EWMA-ICIR) → Dynamic weighting outperforms static fusion. Drop signals with IC < 0.06 (e.g., RSRS, political_impact). Paper-trading (L2) is secondary: Without robust signals, it wastes effort.  

---

### RECOMMENDATIONS  
1. **Activate adaptive weights** (EWMA-ICIR) to replace static `WeightPolicy`.  
2. **Prune signals** with IC < 0.06 (keep factor, news, earnings, macro).  
3. **Refactor registry** with decorator self-registration + lazy-loading.  
4. **Add regime-aware backtesting** (volatility/SPY regimes).  
5. **Deploy L2 paper-trading** only after #1–#3, with Almgren-Chriss costs.  

### VERDICT  
**Yes, but pivot focus:** Activate adaptive weights immediately; drop low-IC signals and registry cruft. Paper-trading is premature until signal edge is proven.