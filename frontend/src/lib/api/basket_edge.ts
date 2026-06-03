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
}

export interface BasketEdgeResponse {
  as_of: string;
  universe_n: number;
  horizons: HorizonEdge[];
}

export const fetchBasketEdge = (opts?: ApiGetOptions) =>
  apiGet<BasketEdgeResponse>("/api/picks/edge", opts);
