export const PICKS_STALE_AFTER_MS = 24 * 60 * 60 * 1000;

/**
 * Re-evaluate snapshot freshness against the browser clock. The backend flag
 * is authoritative when true, but a cached false must not remain fresh after
 * the snapshot crosses the 24-hour boundary on an open page.
 */
export function isPicksSnapshotStale(
  asOf: string | null,
  serverStale: boolean,
  nowMs = Date.now(),
): boolean {
  if (serverStale) return true;
  if (!asOf) return true;
  const asOfMs = Date.parse(asOf);
  if (!Number.isFinite(asOfMs)) return true;
  return nowMs - asOfMs > PICKS_STALE_AFTER_MS;
}
