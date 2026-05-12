// frontend/src/lib/api/alerts.ts
import { apiGet } from "./client";

export interface CronRun {
  started_at: string;
  finished_at: string | null;
  ok: boolean;
  error_count: number;
}

export const fetchCronHealth = () =>
  apiGet<{ cron: Record<string, CronRun[]> }>(`/api/_health/cron`);
