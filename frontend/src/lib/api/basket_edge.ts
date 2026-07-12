// frontend/src/lib/api/basket_edge.ts
import { apiGet, type ApiGetOptions } from "./client";

// One horizon's long-short basket edge. All metrics are null when the horizon
// is `insufficient` (the daily_signals_fast history is too short for that
// horizon's forward window to have observable exits yet) — the UI shows a
// muted "—" / "数据不足" instead of fabricating a number.
export interface HorizonEdge {
  // Trading-day horizon: 5 / 20 / 60.
  horizon: number;
  // Mean per-date Spearman rank-IC between composite and forward return.
  // Honest magnitude is small (|IC| typically < 0.1).
  mean_ic: number | null;
  // mean_ic / std(per-date ICs); null when < 2 dates or zero dispersion.
  ic_ir: number | null;
  // Mean per-date long-short quintile spread, as a per-period return (e.g.
  // 0.012 = +1.2%). Beta-neutral: top-20%-by-composite minus bottom-20%.
  long_short_spread: number | null;
  // Number of trailing dates the aggregation used.
  n_days: number;
  // True when n_days is below the statistical floor (~10): metrics are null.
  insufficient: boolean;
  // 2026-07-12: IC significance (display-only, does not affect ranking)
  ic_t_stat: number | null;
  ic_t_gt2: boolean | null;   // |t| > 2.0 conventional significance
  ic_t_gt3: boolean | null;   // |t| > 3.0 Harvey-Liu-Zhu multiple-testing hurdle
}

export interface BasketEdgeResponse {
  as_of: string;
  universe_n: number;
  horizons: HorizonEdge[];
}

export const fetchBasketEdge = (opts?: ApiGetOptions) =>
  apiGet<BasketEdgeResponse>("/api/picks/edge", opts);

// Portfolio-level realized scoreboard: each trailing day's top/bottom-K basket
// (from the signals as stored THAT day, no lookahead) compounded forward, vs
// the equal-weight universe average, plus the long basket's directional
// hit-rate vs the always-guess-up base rate (the blind-guess baseline).
// null = not enough realized history yet.
export interface PicksScoreboard {
  days: number;
  top_n: number;
  long_cum: number;
  short_cum: number;
  market_cum: number;
  spread_cum: number;
  long_hit_rate: number | null;
  base_rate: number | null;
  // 2026-07-12: cost/turnover/SPY/significance (display-only, does not affect ranking)
  spy_cum: number | null;
  mean_daily_turnover: number | null;
  long_net_cum: number | null;
  cost_bps_used: number;
  breakeven_cost_bps: number | null;
  beta: number | null;
  alpha_ann: number | null;
  alpha_t: number | null;
}

export const fetchPicksScoreboard = (opts?: ApiGetOptions) =>
  apiGet<PicksScoreboard | null>("/api/picks/scoreboard", opts);
