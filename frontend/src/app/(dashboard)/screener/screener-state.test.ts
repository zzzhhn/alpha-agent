import { describe, expect, it } from "vitest";
import { isClassifiedScreenerSector, screenerDraftKey, screenerSectorLabel } from "./screener-state";

const draft = {
  selections: [{ id: "momentum", direction: "long_short", weight: 1 }],
  selectedSectors: new Set(["Technology", "Energy"]),
  excludeInput: "AAPL, TSLA",
  minCap: "10000000000",
  maxCap: "",
  lookback: 60,
  topN: 20,
  combineMethod: "equal_z",
  asOfDate: "",
  neutralize: "none",
};

describe("successful screener result / editable draft boundary", () => {
  it("ignores filter order, ticker case and separators without mutating the draft", () => {
    expect(screenerDraftKey({
      ...draft,
      selectedSectors: new Set(["Energy", "Technology"]),
      excludeInput: "tsla，aapl AAPL",
      minCap: " 10000000000 ",
    })).toBe(screenerDraftKey(draft));
    expect([...draft.selectedSectors]).toEqual(["Technology", "Energy"]);
  });

  it.each([
    { topN: 50 }, { lookback: 120 }, { combineMethod: "user_weighted" },
    { neutralize: "sector" }, { asOfDate: "2026-10-30" },
    { maxCap: "200000000000" }, { minCap: "" },
    { selectedSectors: new Set(["Energy"]) }, { excludeInput: "AAPL" },
    { selections: [] },
    { selections: [{ id: "momentum", direction: "long_short", weight: 2 }] },
    { selections: [{ id: "momentum", direction: "short_only", weight: 1 }] },
  ])("detects an edited input while preserving the captured result key: %j", (change) => {
    const captured = screenerDraftKey(draft);
    expect(screenerDraftKey({ ...draft, ...change })).not.toBe(captured);
    expect(screenerDraftKey(draft)).toBe(captured);
  });
});

describe("display-only sector localization", () => {
  it.each([
    ["Communication Services", "通信服务"], ["Consumer Discretionary", "可选消费"],
    ["Consumer Staples", "必需消费"], ["Energy", "能源"], ["Financials", "金融"],
    ["Health Care", "医疗保健"], ["Industrials", "工业"], ["Information Technology", "信息技术"],
    ["Materials", "原材料"], ["Real Estate", "房地产"], ["Utilities", "公用事业"],
    ["Technology", "信息技术"], ["Financial Services", "金融"], ["Healthcare", "医疗保健"],
    ["Consumer Cyclical", "可选消费"], ["Consumer Defensive", "必需消费"], ["Basic Materials", "原材料"],
  ])("translates %s without changing its canonical English value", (sector, expected) => {
    expect(screenerSectorLabel(sector, "zh")).toBe(expected);
    expect(screenerSectorLabel(sector, "en")).toBe(sector);
    expect(isClassifiedScreenerSector(sector)).toBe(true);
  });

  it.each([null, undefined, "", "  ", "Unknown", "Unclassified", "N/A", "NA", "未知", "未分类"])("keeps missing classification explicit and unselectable: %s", (sector) => {
    expect(isClassifiedScreenerSector(sector)).toBe(false);
    expect(screenerSectorLabel(sector, "zh")).toBe("未分类");
    expect(screenerSectorLabel(sector, "en")).toBe("Unclassified");
  });

  it("retains unfamiliar real classifications rather than inventing a translation", () => {
    expect(screenerSectorLabel("Specialty", "zh")).toBe("Specialty");
  });
});
