// frontend/src/lib/api/admin.ts
//
// Typed client for the backend admin route that dispatches the GitHub Actions
// cron workflow. Used by the in-app "Refresh now" button so users don't have
// to wait for the every-2h scheduled cron tick.
import { apiGet, apiPost } from "./client";

export interface RefreshResponse {
  ok: boolean;
  request_id: string | null;
  dispatched_at: string | null;
  eta_minutes: number | null;
  reason: string | null;
  last_run_started_at: string | null;
}

export interface LastRefreshResponse {
  fast_intraday: string | null;
  fast_intraday_finished_at: string | null;
  slow_daily: string | null;
  slow_daily_finished_at: string | null;
  recommendation_publish: {
    started_at: string | null;
    finished_at: string | null;
    ok: boolean | null;
    status:
      | "published"
      | "no_op_same_market_date"
      | "health_gate_failed"
      | "failed";
    run_id: number | null;
    market_date: string | null;
    reason: string | null;
    request_id: string | null;
  } | null;
}

export const triggerRefresh = (job: "fast_intraday" | "slow_daily" | "both" = "fast_intraday") =>
  apiPost<RefreshResponse, { job: string }>("/api/admin/refresh", { job });

export const fetchLastRefresh = () =>
  apiGet<LastRefreshResponse>("/api/admin/last_refresh");
