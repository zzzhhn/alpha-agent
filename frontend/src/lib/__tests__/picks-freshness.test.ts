import { describe, expect, it } from "vitest";
import { isPicksSnapshotStale, picksSnapshotStatus } from "../picks-freshness";

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

  it("never calls an empty lookup with no snapshot timestamp current", () => {
    expect(picksSnapshotStatus(null, false)).toBe("unknown");
    expect(picksSnapshotStatus("not-a-date", false)).toBe("unknown");
    expect(picksSnapshotStatus(asOf, true)).toBe("stale");
    expect(picksSnapshotStatus(asOf, false)).toBe("current");
  });
});
