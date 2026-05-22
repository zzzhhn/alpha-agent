// frontend/src/lib/api/evolution.ts
// Read-only Evolution dashboard client (Phase 2c). Targets the /api/evolution
// backend router via apiGet (full /api path), matching signal_health.ts etc.
// NOT the /api/v1 fetchJson client in lib/api.ts.
import { apiGet, apiPost, type ApiGetOptions } from "./client";

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

// Proposal types for methodology-proposal approval workflow (Phase 2b).
export interface Proposal {
  id: number;
  field: string;
  old_value: unknown;
  new_value: unknown;
  evidence: Record<string, unknown>;
  changed_at: string;
  status: string;
}
export interface ProposalsResponse {
  proposals: Proposal[];
}

// Auth for these mutations is handled automatically by the Next.js middleware,
// which injects the Bearer token on same-origin /api/* requests (browser-side).
export const fetchProposals = (opts?: ApiGetOptions) =>
  apiGet<ProposalsResponse>("/api/evolution/proposals", opts);

export const approveProposal = (id: number) =>
  apiPost<unknown, Record<string, never>>(`/api/evolution/proposals/${id}/approve`, {});

export const rejectProposal = (id: number) =>
  apiPost<unknown, Record<string, never>>(`/api/evolution/proposals/${id}/reject`, {});

export const rollbackChange = (id: number) =>
  apiPost<unknown, Record<string, never>>(`/api/evolution/proposals/${id}/rollback`, {});
