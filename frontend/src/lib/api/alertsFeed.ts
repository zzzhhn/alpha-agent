// frontend/src/lib/api/alertsFeed.ts
//
// Typed client for the M4b /api/alerts/recent endpoint. Distinct file
// from the existing alerts.ts (which only knows cron-run history) so we
// can deprecate that one cleanly after B1c lands.
import { apiGet } from "./client";

export interface AlertRow {
  id: number;
  ticker: string;
  type: string;
  payload: Record<string, unknown> | unknown[] | null;
  dedup_bucket: number;
  created_at: string; // ISO 8601
}

export interface AlertsRecentResponse {
  alerts: AlertRow[];
}

export const fetchAlertsRecent = (opts: { ticker?: string; limit?: number } = {}) => {
  const params = new URLSearchParams();
  if (opts.ticker) params.set("ticker", opts.ticker.toUpperCase());
  if (opts.limit != null) params.set("limit", String(opts.limit));
  const qs = params.toString();
  return apiGet<AlertsRecentResponse>(
    `/api/alerts/recent${qs ? `?${qs}` : ""}`,
  );
};
