// frontend/src/lib/api/signal_health.ts
import { apiGet } from "./client";

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
}

export const fetchSignalHealth = () =>
  apiGet<{ signals: SignalHealthEntry[] }>("/api/_health/signals");
