import { describe, expect, it } from "vitest";
import { factorSourceNote, readFactorSource } from "@/lib/factor-source";

const raw = {
  z: 1.15,
  factor_source: {
    expression: "group_neutralize(zscore(ts_zscore(volume,20)),sector)",
    is_custom: true,
    panel: "frozen_research_parquet",
    data_date: "2026-10-30",
  },
};

describe("factor source disclosure", () => {
  it("reads the backend provenance block", () => {
    expect(readFactorSource(raw)).toEqual({
      expression: "group_neutralize(zscore(ts_zscore(volume,20)),sector)",
      isCustom: true,
      panel: "frozen_research_parquet",
      dataDate: "2026-10-30",
    });
  });

  it("flags a frozen panel older than the card market date", () => {
    const note = factorSourceNote(readFactorSource(raw), "2026-11-10", "zh");
    expect(note).toEqual({ text: "自定义表达式 · 冻结研究面板 · 数据截至 2026-10-30", stale: true });
  });

  it("is not stale when the live panel matches the market date", () => {
    const note = factorSourceNote(
      { expression: null, isCustom: false, panel: "live_daily_prices", dataDate: "2026-11-10" },
      "2026-11-10",
      "en",
    );
    expect(note).toEqual({ text: "Preset expression · daily prices · data through 2026-11-10", stale: false });
  });

  it("returns null for legacy rows without provenance", () => {
    expect(readFactorSource({ z: 1 })).toBeNull();
    expect(factorSourceNote(null, "2026-11-10", "zh")).toBeNull();
  });
});
