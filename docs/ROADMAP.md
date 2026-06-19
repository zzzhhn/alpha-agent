# alpha-agent roadmap

Single-user quantitative equity rating engine. Research-only (no live execution).
This file tracks direction; detailed plans live in their own docs (linked).

## Shipped recently

- **RSRS timing factor** — price-based (high~low slope, z-scored) cross-sectional
  diversifier, validated weak-but-positive (~0.043 IC @20d, M=126) and fused at a
  small capped weight. `signals/rsrs.py`, `scripts/rsrs_validation.py`.
- **Directional consistency** on picks (5d/1m/1y/all next-day hit-rate, dash when thin).
- **Dead-price-feed guard** — untradeable/delisted tickers (no close in last N
  sessions) dropped from the default ranking; cron now surfaces skipped tickers.

## Planned (ordered)

### 1. Signal-registry consolidation
See `docs/signal-registry-consolidation-plan.md`. Replace the ~10 hand-maintained
signal-registration sites (7 backend + 3 frontend mirrors) with a single
`SIGNAL_REGISTRY` everything derives from; codegen the frontend mirrors; delete
dead `llm/_legacy/`. Structural, zero behavior change, phased.

### 2. L2 forward paper-trading (verification layer)
The honest, end-to-end answer to "do the engine's calls actually work?" without
risking real money. Three levels of verification, only L1+L2 in scope:

- **L1 (have):** historical / IC backtest (`ic_engine`, `consistency`). Statistical,
  has look-ahead/overfit risk.
- **L2 (build this):** forward paper-trading. Take the engine's REAL daily picks,
  construct a virtual portfolio (e.g. long the top-N OW/BUY names, optional short
  the bottom-N), mark it to market daily off `daily_prices`, and track the
  cumulative equity curve vs a benchmark (SPY). It is forward and look-ahead-free
  (only uses data as it arrives), needs no broker / no paid data / no real money,
  and is largely a deterministic accounting layer over data we already have
  (picks + daily_prices). This is the natural extension of the earlier
  forward-IC-tracking / hindsight-basket work. Deliverables: a portfolio-construction
  rule, a daily mark-to-market cron, a positions/pnl table, an equity-curve UI.
- **L3 (NOT now):** real-money live execution via a broker API. Gated on L2 showing
  a forward edge over a meaningful window. Risk + broker/OMS/reconciliation surface;
  free data is NOT the blocker (Alpaca free tier covers paper+live data), the
  execution surface is. Revisit only after L2.

## Backlog / later

- GA-based factor mining as a second discovery engine feeding the existing
  sandbox/validation (complements the LLM proposer). (RedNote note 5)
- Explicit money-management / position-sizing stage (formalize the Kelly sizing
  now buried in confidence). (RedNote note 3 step 5 + note 1 "risk assessment")
- Re-tune / promote-or-drop RSRS once `ic_backtest_monthly` accrues its live IC.
