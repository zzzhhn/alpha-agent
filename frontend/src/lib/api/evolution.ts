// frontend/src/lib/api/evolution.ts
// Read-only Evolution dashboard client (Phase 2c). Targets the /api/evolution
// backend router via apiGet (full /api path), matching signal_health.ts etc.
// NOT the /api/v1 fetchJson client in lib/api.ts.
import { apiGet, type ApiGetOptions } from "./client";

export interface IcTrendPoint {
  computed_at: string;
  ic: number;
  n: number;
}
export interface IcTrendSeries {
  signal_name: string;
  points: IcTrendPoint[];
}
export interface IcTrendResponse {
  window_days: number;
  series: IcTrendSeries[];
}

export interface EvolutionWeight {
  signal_name: string;
  status: "live" | "shadow";
  weight: number;
  reason: string | null;
  consecutive_bad_windows: number;
  shadow_streak: number;
  last_updated: string | null;
}
export interface EvolutionWeightsResponse {
  weights: EvolutionWeight[];
}

export interface CalibrationBucket {
  lo: number;
  hi: number;
  hit_rate: number | null;
  brier: number | null;
  n: number;
}
export interface EvolutionCalibration {
  as_of: string | null;
  n_pairs: number;
  applied: boolean;
  isotonic_map?: { x: number[]; y: number[] };
  buckets: CalibrationBucket[];
}

export interface EvolutionChange {
  id: number;
  source: string;
  changed_at: string;
  rollback_of: number | null;
  new_value: string;
}
export interface EvolutionChangesResponse {
  changes: EvolutionChange[];
}

export const fetchIcTrend = (windowDays = 30, opts?: ApiGetOptions) =>
  apiGet<IcTrendResponse>(`/api/evolution/ic_trend?window_days=${windowDays}`, opts);

export const fetchEvolutionWeights = (opts?: ApiGetOptions) =>
  apiGet<EvolutionWeightsResponse>("/api/evolution/weights", opts);

export const fetchEvolutionCalibration = (opts?: ApiGetOptions) =>
  apiGet<EvolutionCalibration>("/api/evolution/calibration", opts);

export const fetchEvolutionChanges = (limit = 50, opts?: ApiGetOptions) =>
  apiGet<EvolutionChangesResponse>(`/api/evolution/changes?limit=${limit}`, opts);
