import { describe, expect, it } from "vitest";
import { isPicksSnapshotStale, PICKS_STALE_AFTER_MS } from "../picks-freshness";

describe("isPicksSnapshotStale", () => {
  const asOf = "2026-08-01T00:00:00Z";
  const base = Date.parse(asOf);

  it("ages a cached fresh response against the live clock", () => {
    expect(isPicksSnapshotStale(asOf, false, base + PICKS_STALE_AFTER_MS)).toBe(false);
    expect(isPicksSnapshotStale(asOf, false, base + PICKS_STALE_AFTER_MS + 1)).toBe(true);
  });

  it("keeps the backend stale flag authoritative", () => {
    expect(isPicksSnapshotStale(asOf, true, base)).toBe(true);
  });

  it("fails closed for a missing or invalid timestamp", () => {
    expect(isPicksSnapshotStale(null, false, base)).toBe(true);
    expect(isPicksSnapshotStale("not-a-date", false, base)).toBe(true);
  });
});
