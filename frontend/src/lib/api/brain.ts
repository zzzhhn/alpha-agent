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
