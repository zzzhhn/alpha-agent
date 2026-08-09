// Shared "refresh dispatch in-flight" state for the picks page.
//
// A "立即刷新 / Refresh now" click dispatches a cron run that takes ~18 min and
// updates the universe PROGRESSIVELY. Two components coordinate through this
// module so the UX during that window is sane:
//   - RefreshButton: locks the button for the whole window (no re-dispatch) and
//     shows ETA progress, then polls for the publish result.
//   - PicksBrowser: freezes the default board to a pre-dispatch snapshot (so a
//     mid-window reload doesn't show a different half-updated list each time),
//     then refreshes only after publication reaches a terminal state.
//
// Same-tab coordination uses a CustomEvent (storage events only fire
// cross-tab); cross-reload persistence uses localStorage.
import type { PicksResponse } from "@/lib/api/picks";

export const DISPATCH_KEY = "alpha-agent:dispatch";
export const SNAPSHOT_KEY = "alpha-agent:picks-snapshot";
export const DISPATCH_EVENT = "alpha-agent:dispatch-start";
export const REFRESH_SETTLED_EVENT = "alpha-agent:refresh-settled";

export type PublishStatus =
  | "published"
  | "no_op_same_market_date"
  | "health_gate_failed"
  | "failed";

export type RefreshSettledDetail = {
  status: PublishStatus;
  runId: number | null;
  marketDate: string | null;
};

export type Dispatch = {
  at: number;
  etaMin: number;
  serverDispatchedAt: string | null;
  requestId: string | null;
};
export type PicksSnapshot = PicksResponse;

export function loadDispatch(): Dispatch | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(DISPATCH_KEY);
    if (!raw) return null;
    const p = JSON.parse(raw) as Partial<Dispatch>;
    if (typeof p.at !== "number" || typeof p.etaMin !== "number") return null;
    // Drop anything well past its ETA so an old dispatch never lingers.
    if (Date.now() - p.at > (p.etaMin + 30) * 60_000) {
      clearDispatch();
      return null;
    }
    return {
      at: p.at,
      etaMin: p.etaMin,
      serverDispatchedAt:
        typeof p.serverDispatchedAt === "string" ? p.serverDispatchedAt : null,
      requestId: typeof p.requestId === "string" ? p.requestId : null,
    };
  } catch {
    return null;
  }
}

export function saveDispatch(
  at: number,
  etaMin: number,
  serverDispatchedAt: string | null,
  requestId: string | null,
): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(
      DISPATCH_KEY,
      JSON.stringify({ at, etaMin, serverDispatchedAt, requestId }),
    );
  } catch {
    // localStorage can be unavailable (private mode); degrade silently.
  }
}

export function clearDispatch(): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.removeItem(DISPATCH_KEY);
    localStorage.removeItem(SNAPSHOT_KEY);
  } catch {
    /* ignore */
  }
}

/**
 * Keep the dispatch pending through the ETA plus a bounded verification grace
 * period. Publication status, not elapsed time, normally clears it earlier.
 */
export function isInFlight(d: Dispatch | null, now: number = Date.now()): boolean {
  return d != null && now < d.at + (d.etaMin + 30) * 60_000;
}

export function saveSnapshot(s: PicksSnapshot): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(SNAPSHOT_KEY, JSON.stringify(s));
  } catch {
    /* ignore */
  }
}

export function loadSnapshot(): PicksSnapshot | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(SNAPSHOT_KEY);
    return raw ? (JSON.parse(raw) as PicksSnapshot) : null;
  } catch {
    return null;
  }
}
