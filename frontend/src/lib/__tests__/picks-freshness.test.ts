import { describe, expect, it } from "vitest";
import { isPicksSnapshotStale } from "../picks-freshness";

describe("isPicksSnapshotStale", () => {
  const asOf = "2026-08-01T00:00:00Z";
  it("does not re-age a session-valid snapshot against wall-clock time", () => {
    expect(isPicksSnapshotStale(asOf, false)).toBe(false);
  });

  it("keeps the backend stale flag authoritative", () => {
    expect(isPicksSnapshotStale(asOf, true)).toBe(true);
  });

  it("fails closed for a missing or invalid timestamp", () => {
    expect(isPicksSnapshotStale(null, false)).toBe(true);
    expect(isPicksSnapshotStale("not-a-date", false)).toBe(true);
  });
});
