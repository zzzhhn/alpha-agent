import { describe, expect, it } from "vitest";
import { formatZonedDateTime } from "../format-datetime";
import { gradeBand, gradeExplanation } from "../grade-method";
import { parsePicksView } from "../picks-view-state";
import type { GradeMethod } from "../api/picks";
const method: GradeMethod = { version: "test-from-api", bands: [
  { grade: "A+", min_z: 2.25 }, { grade: "D", min_z: -0.75 }, { grade: "F", min_z: null },
], dimensions: { Momentum: ["factor"] }, min_universe: 20, flatness_floor: 1e-6, definition: "", missing_semantics: [] };

describe("exchange timestamps and calendar boundaries", () => {
  it.each([
    ["2026-03-08T06:59:00Z", "2026-03-08 01:59"],
    ["2026-03-08T07:00:00Z", "2026-03-08 03:00"],
    ["2026-11-01T05:59:00Z", "2026-11-01 01:59"],
    ["2026-11-01T06:00:00Z", "2026-11-01 01:00"],
    ["2026-11-11T00:30:00Z", "2026-11-10 19:30"],
  ])("formats %s in DST-correct New York", (instant, expected) => {
    expect(formatZonedDateTime(instant, "America/New_York")).toBe(expected);
  });
  it("handles midnight, explicit offsets and invalid values", () => {
    expect(formatZonedDateTime("2026-11-10T16:00:00Z", "Asia/Shanghai")).toBe("2026-11-11 00:00");
    expect(formatZonedDateTime("2026-11-11T00:00:00+08:00", "UTC")).toBe("2026-11-10 16:00");
    expect(formatZonedDateTime(null)).toBe("—");
    expect(formatZonedDateTime("invalid")).toBe("—");
    expect(formatZonedDateTime("2026-11-10", "bad-zone")).toBe("—");
  });
});
describe("API-driven grade explanation", () => {
  it("honors API bands including strict F and inclusive D without client thresholds", () => {
    expect(gradeBand("F", method)).toBe("z < -0.75");
    expect(gradeBand("D", method)).toBe("-0.75 ≤ z < 2.25");
    expect(gradeBand("A+", method)).toBe("z ≥ 2.25");
    expect(gradeBand("A+")).toBe("—");
  });
  it("distinguishes unrecorded snapshots from ungradeable null and zero", () => {
    expect(gradeExplanation("动量", "A+", undefined, method, true)).toContain("该快照未记录分值");
    expect(gradeExplanation("动量", "—", null, method, true)).toContain("不可评级");
    expect(gradeExplanation("Momentum", "D", 0, method, false)).toContain("z = 0.000");
  });
});
describe("return-state validation", () => {
  const state = { version: 1, ticker: "NVDA", search: "NV", mode: "long", side: "short", page: 3, pageSize: 25, scroll: 150, tableScroll: 90, data: { picks: [] } };
  it("keeps query, policy, side, pagination and both scroll positions", () => {
    expect(parsePicksView(JSON.stringify(state))).toEqual(state);
  });
  it.each([null, "{", JSON.stringify({ ...state, page: -1 }), JSON.stringify({ ...state, pageSize: 999 }), JSON.stringify({ ...state, mode: "unknown" })])("falls back safely for invalid storage %s", raw => {
    expect(parsePicksView(raw)).toBeNull();
  });
});
