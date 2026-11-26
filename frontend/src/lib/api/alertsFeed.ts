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
  // Same ticker + type + New York date are folded into one group; the item
  // carries the newest member and the complete set observed at read time.
  occurrences?: number;
  first_seen_at?: string | null;
  last_seen_at?: string | null;
  member_ids?: number[];
  group_id?: string | null;
  group_token?: string | null;
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
  next_offset?: number | null;
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

export const fetchAlertInbox = (limit = 50, offset = 0) => {
  const params = new URLSearchParams({ limit: String(limit) });
  if (offset) params.set("offset", String(offset));
  return apiGet<AlertInboxResponse>(`/api/alerts/inbox?${params}`);
};

export const setAlertState = (
  alertId: number,
  body: {
    status: AlertWorkflowStatus;
    snooze_until?: string | null;
    note?: string | null;
  },
) => apiPost<AlertTriageState, typeof body>(`/api/alerts/${alertId}/state`, body);

export interface AlertBatchStateResponse {
  updated: number;
  states: Record<string, AlertTriageState>;
}

/** Legacy explicit-id endpoint for inbox responses issued before group credentials. */
export const setAlertStatesBatch = (body: {
  alert_ids: number[];
  status: AlertWorkflowStatus;
  snooze_until?: string | null;
  note?: string | null;
}) => apiPost<AlertBatchStateResponse, typeof body>("/api/alerts/state/batch", body);

/** Member ids of a (possibly grouped) inbox item; legacy items fall back to their own id. */
export const alertMemberIds = (item: Pick<AlertInboxItem, "id" | "member_ids">): number[] =>
  item.member_ids && item.member_ids.length ? item.member_ids : [item.id];


interface GroupStateReceipt {
  updated: number;
  state: AlertTriageState;
  undo_token: string | null;
}

type AlertStateChange = {
  status: AlertWorkflowStatus;
  snooze_until?: string | null;
  note?: string | null;
};

export async function applyInboxAlertState(
  item: Pick<AlertInboxItem, "id" | "member_ids" | "group_token" | "state">,
  change: AlertStateChange,
): Promise<{ state: AlertTriageState; updated: number; undo: (() => Promise<AlertTriageState>) | null }> {
  const groupToken = item.group_token;
  if (groupToken) {
    const body = { group_token: groupToken, ...change };
    const receipt = await apiPost<GroupStateReceipt, typeof body>("/api/alerts/state/group", body);
    const undoToken = receipt.undo_token;
    return {
      state: receipt.state,
      updated: receipt.updated,
      undo: undoToken ? async () => {
        const originalWindow = { group_token: groupToken, undo_token: undoToken };
        return (await apiPost<GroupStateReceipt, typeof originalWindow>(
          "/api/alerts/state/group/undo", originalWindow,
        )).state;
      } : null,
    };
  }
  const ids = alertMemberIds(item);
  const save = async (body: AlertStateChange) => ids.length === 1
    ? setAlertState(ids[0], body)
    : (await setAlertStatesBatch({ alert_ids: ids, ...body })).states[String(item.id)];
  return {
    state: await save(change),
    updated: ids.length,
    undo: () => save({ status: item.state.status, snooze_until: item.state.snooze_until, note: item.state.note }),
  };
}

export function appendAlertInboxPage(current: AlertInboxResponse, page: AlertInboxResponse): AlertInboxResponse {
  const known = new Set(current.alerts.map(item => item.group_id ?? item.id));
  const alerts = [...current.alerts, ...page.alerts.filter(item => !known.has(item.group_id ?? item.id))];
  alerts.sort((a, b) => b.triage_score - a.triage_score || b.created_at.localeCompare(a.created_at) || b.id - a.id);
  return { ...current, alerts, as_of: page.as_of, next_offset: page.next_offset };
}
