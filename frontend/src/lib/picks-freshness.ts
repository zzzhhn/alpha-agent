/**
 * Canonical recommendation freshness is exchange-session aware on the backend.
 * Do not re-age it against the browser's wall clock because a healthy Friday
 * close remains the latest completed XNYS session throughout a weekend or
 * market holiday.
 */
export function isPicksSnapshotStale(
  asOf: string | null,
  serverStale: boolean,
): boolean {
  if (serverStale) return true;
  if (!asOf) return true;
  return !Number.isFinite(Date.parse(asOf));
}
