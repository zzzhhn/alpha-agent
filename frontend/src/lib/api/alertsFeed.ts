// frontend/src/lib/api/alertsFeed.ts
//
// Typed client for the M4b /api/alerts/recent endpoint. Distinct file
// from the existing alerts.ts (which only knows cron-run history) so we
// can deprecate that one cleanly after B1c lands.
import { apiGet, apiPost } from "./client";

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

export type AlertSeverity = "critical" | "warning" | "info";
export type AlertRelevance =
  | "position"
  | "recommendation"
  | "market"
  | "watchlist"
  | "record";
export type AlertWorkflowStatus = "open" | "snoozed" | "resolved";

export interface AlertContext {
  in_position: boolean;
  in_recommendation: boolean;
  in_watchlist: boolean;
  recommendation_rank: number | null;
  recommendation_run_id: number | null;
  recommendation_market_date: string | null;
}

export interface AlertTriageState {
  status: AlertWorkflowStatus;
  snooze_until: string | null;
  resolved_at: string | null;
  note: string | null;
  updated_at: string | null;
}

export interface AlertInboxItem extends AlertRow {
  severity: AlertSeverity;
  relevance: AlertRelevance;
  triage_score: number;
  freshness_score: number;
  confidence_score: number;
  confidence: "high" | "medium" | "low";
  source_count: number;
  stale: boolean;
  context: AlertContext;
  state: AlertTriageState;
}

export interface AlertInboxResponse {
  alerts: AlertInboxItem[];
  counts: {
    needs_action: number;
    watch: number;
    record: number;
    resolved: number;
  };
  as_of: string;
  source_status: "fresh" | "stale" | "empty";
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

export const fetchAlertInbox = (limit = 50) =>
  apiGet<AlertInboxResponse>(`/api/alerts/inbox?limit=${limit}`);

export const setAlertState = (
  alertId: number,
  body: {
    status: AlertWorkflowStatus;
    snooze_until?: string | null;
    note?: string | null;
  },
) => apiPost<AlertTriageState, typeof body>(`/api/alerts/${alertId}/state`, body);
