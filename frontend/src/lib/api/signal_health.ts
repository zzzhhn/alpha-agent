// frontend/src/lib/api/signal_health.ts
import { apiGet, type ApiGetOptions } from "./client";

export interface SignalHealthEntry {
  name: string;
  live_ic_30d: number | null;
  live_ic_60d: number | null;
  live_ic_90d: number | null;
  weight_current: number | null;
  tier: "green" | "yellow" | "red" | "insufficient_data" | "unknown";
  last_success: string | null;
  last_error: string | null;
  error_count_24h: number;
  // B1 (2026-05-19) joint diagnostics derived from signal_ic_history on
  // the 30d window. ICIR = ic_mean / ic_std (stability gauge); IR =
  // ICIR × √(252/30) (annualized info ratio). n_obs is the count of IC
  // observations the 30d aggregation used (max 90). All null/0 when
  // history < 2 observations.
  icir_30d?: number | null;
  ir_30d?: number | null;
  n_obs_30d?: number;
}

export const fetchSignalHealth = (opts?: ApiGetOptions) =>
  apiGet<{ signals: SignalHealthEntry[] }>("/api/_health/signals", opts);
