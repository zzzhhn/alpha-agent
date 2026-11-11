import { describe, expect, it } from "vitest";
import { calibrationBasisText } from "@/components/stock/RatingBadge";

describe("calibration basis text", () => {
  it("states sample size, level count and fit date", () => {
    expect(calibrationBasisText({ nPairs: 95, levels: 4, asOf: "2026-11-11T01:45:36Z" }, "zh"))
      .toBe("校准样本 95 个 · 4 档 · 拟合于 2026-11-11");
    expect(calibrationBasisText({ nPairs: 981, levels: 7, asOf: "2026-09-26T00:18:22Z" }, "en"))
      .toBe("981 calibration samples · 7 levels · fitted 2026-09-26");
  });

  it("is explicit when the basis is unknown", () => {
    expect(calibrationBasisText(null, "zh")).toBe("校准样本与拟合时间未知");
    expect(calibrationBasisText({ nPairs: null, levels: null, asOf: null }, "en"))
      .toBe("Calibration sample size and fit date unknown");
  });
});
