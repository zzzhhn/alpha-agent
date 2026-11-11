import { apiGet, ApiException } from "@/lib/api/client";
import type { ServiceState } from "@/components/tm/TmServiceStatus";

export const SERVICE_HEALTH_CACHE_KEY = "alphacore.service-health.v1";
const CACHE_MAX_AGE_MS = 120_000;
const RESOLVED_STATES: readonly ServiceState[] = ["healthy", "degraded", "partial", "unknown", "unavailable"];

/** Pure storage boundary: malformed, future-dated and expired entries are ignored. */
export function readCachedServiceHealth(raw: string | null, now = Date.now()): ServiceState | null {
  if (!raw) return null;
  try {
    const cached: unknown = JSON.parse(raw);
    if (typeof cached !== "object" || cached === null) return null;
    const { state, timestamp } = cached as { state?: unknown; timestamp?: unknown };
    if (typeof state !== "string" || !RESOLVED_STATES.includes(state as ServiceState)) return null;
    if (typeof timestamp !== "number" || !Number.isFinite(timestamp)) return null;
    const age = now - timestamp;
    return age >= 0 && age < CACHE_MAX_AGE_MS ? state as ServiceState : null;
  } catch {
    return null;
  }
}

export function serializeServiceHealthCache(state: ServiceState, timestamp = Date.now()): string | null {
  return RESOLVED_STATES.includes(state) ? JSON.stringify({ state, timestamp }) : null;
}

export function isHealthTimeout(error: unknown): boolean {
  // apiGet uses AbortSignal.timeout, whose rejection is a TimeoutError.
  return !(error instanceof ApiException) && error instanceof Error && error.name === "TimeoutError";
}

async function readConnectivity(): Promise<{ db?: string }> {
  try {
    return await apiGet<{ db?: string }>("/api/_health", { timeoutMs: 12_000 });
  } catch (error) {
    if (!isHealthTimeout(error)) throw error;
    // Health reads only: give a cold server time to start, then retry once.
    await new Promise<void>((resolve) => setTimeout(resolve, 15_000));
    return apiGet<{ db?: string }>("/api/_health", { timeoutMs: 12_000 });
  }
}

/** Connectivity and pipeline freshness are independent observations. */
export async function readSystemHealth(): Promise<ServiceState> {
  const [health, pipeline] = await Promise.allSettled([
    readConnectivity(),
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
