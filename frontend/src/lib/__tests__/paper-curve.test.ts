import { describe, expect, it } from "vitest";
import { normalizePaperCurve } from "../paper-curve";

describe("normalizePaperCurve", () => {
  it("puts portfolio value and SPY on the same 100-based scale", () => {
    const rows = normalizePaperCurve([
      { date: "2026-07-30", portfolio_value: 1_000_000, benchmark_index: 100 },
      { date: "2026-07-31", portfolio_value: 1_010_000, benchmark_index: 100.5 },
    ]);
    expect(rows.map((row) => row.portfolio_index)).toEqual([100, 101]);
    expect(rows.map((row) => row.benchmark_index)).toEqual([100, 100.5]);
  });

  it("returns no chart points when a valid base cannot be established", () => {
    expect(normalizePaperCurve([])).toEqual([]);
    expect(normalizePaperCurve([
      { date: "2026-07-30", portfolio_value: 0, benchmark_index: 100 },
    ])).toEqual([]);
  });

  it("preserves missing marks as dated gaps instead of zero returns", () => {
    const rows = normalizePaperCurve([
      { date: "2026-10-28", portfolio_value: 100_000, benchmark_index: 100 },
      { date: "2026-10-29", portfolio_value: null, benchmark_index: null },
      { date: "2026-10-30", portfolio_value: 102_000, benchmark_index: 101 },
    ]);
    expect(rows.map(row=>row.date)).toEqual(["2026-10-28", "2026-10-29", "2026-10-30"]);
    expect(rows.map(row=>row.portfolio_index)).toEqual([100, null, 102]);
    expect(rows.map(row=>row.benchmark_index)).toEqual([100, null, 101]);
  });
});
