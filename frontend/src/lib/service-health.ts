import { apiGet, ApiException } from "@/lib/api/client";
import type { ServiceState } from "@/components/tm/TmServiceStatus";

/** Connectivity and pipeline freshness are independent observations. */
export async function readSystemHealth(): Promise<ServiceState> {
  const [health, pipeline] = await Promise.allSettled([
    apiGet<{ db?: string }>("/api/_health", { timeoutMs: 12_000 }),
    apiGet<{ overall?: string }>("/api/_health/dag", { timeoutMs: 12_000 }),
  ]);
  if (health.status === "rejected") {
    // A client timeout/offline/auth/rate-limit failure is not proof of an outage.
    return health.reason instanceof ApiException && health.reason.status >= 500
      ? "unavailable" : "unknown";
  }
  if (health.value?.db === "down") return "unavailable";
  if (health.value?.db !== "ok") return "unknown";
  if (pipeline.status === "rejected") return "partial";
  if (pipeline.value?.overall === "healthy") return "healthy";
  if (pipeline.value?.overall === "degraded") return "degraded";
  return "partial";
}
