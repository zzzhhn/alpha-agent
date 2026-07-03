// WorldQuant BRAIN credential vault client (Phase E2). The password is only ever
// sent on save; the status/test endpoints never return it.
import { apiGet, apiPost, type ApiGetOptions } from "./client";

export interface BrainStatus {
  connected: boolean;
  username_last4?: string;
  saved_at?: string | null;
}

export interface BrainTestResult {
  ok: boolean;
  error?: string;
}

export const fetchBrainStatus = (opts?: ApiGetOptions) =>
  apiGet<BrainStatus>("/api/brain/credentials", opts);

export const saveBrainCredentials = (username: string, password: string) =>
  apiPost<
    { connected: boolean; username_last4: string },
    { username: string; password: string }
  >("/api/brain/credentials", { username, password });

export const testBrainConnection = () =>
  apiPost<BrainTestResult, Record<string, never>>(
    "/api/brain/credentials/test",
    {},
  );

// Phase E4/E5: one BRAIN mining result. Outcome buckets the candidate after it
// was simulated on the real platform.
export type BrainOutcome = "passed" | "flagged" | "rejected" | "sim_error";

export interface BrainAlpha {
  id: number;
  expression: string;
  settings: Record<string, unknown>;
  alpha_id: string | null;
  sharpe: number | null;
  fitness: number | null;
  turnover: number | null;
  drawdown: number | null;
  self_correlation: number | null;
  self_correlation_with: string | null;
  outcome: BrainOutcome;
  detail: string | null;
  created_at: string | null;
  submitted_at: string | null;
  brain_status: string | null;
}

export interface BrainSubmitResult {
  ok: boolean;
  brain_status: string;
  alpha_id: string;
}

export const fetchBrainAlphas = (limit = 100, opts?: ApiGetOptions) =>
  apiGet<{ alphas: BrainAlpha[] }>(`/api/brain/alphas?limit=${limit}`, opts);

export const submitBrainAlpha = (rowId: number) =>
  apiPost<BrainSubmitResult, Record<string, never>>(
    `/api/brain/alphas/${rowId}/submit`,
    {},
  );
