// frontend/src/lib/__tests__/action-box.test.ts
// Regression for 2026-05-18 ATR-unit bug: technicals.py stores ATR as a
// ratio (raw_atr / close), but deriveActionBox treated it as dollars →
// entry/stop differed by cents, not $-units. Cover three shapes:
//   (1) ratio in atr14 only (legacy backend, < 1) → infer dollar via px
//   (2) explicit atr_dollar from new backend → use as-is
//   (3) dollar in atr14 (>= 1) → use directly
import { describe, it, expect } from "vitest";
import { deriveActionBox } from "@/lib/action-box";

describe("deriveActionBox ATR-unit handling", () => {
  it("upscales ratio atr14 (< 1) by current price", () => {
    // ATR 2% of a $200 stock → effective ATR-dollar = $4
    // entry width = ATR * 1.0 = $4, stop distance = ATR * 1.5 = $6
    const out = deriveActionBox({
      currentPrice: 200,
      atr14: 0.02,
      atrDollar: null,
      analystTarget: 220,
      high180d: 215,
      confidence: 0.6,
    });
    expect(out.entryLow).toBeCloseTo(198, 1);
    expect(out.entryHigh).toBeCloseTo(202, 1);
    expect(out.stop).toBeCloseTo(194, 1);
    // RR = (target - mid) / (mid - stop) = (Math.min(220, 215*1.05) - 200) / 6
    // = min(220, 225.75) - 200 = 20 / 6 ≈ 3.33
    expect(out.rrRatio).toBeCloseTo(3.33, 1);
  });

  it("prefers explicit atr_dollar over atr14 ratio", () => {
    const out = deriveActionBox({
      currentPrice: 200,
      atr14: 0.02,
      atrDollar: 5,  // backend explicitly tells us ATR is $5
      analystTarget: 220,
      high180d: null,
      confidence: 0.6,
    });
    expect(out.entryLow).toBeCloseTo(197.5, 1);
    expect(out.entryHigh).toBeCloseTo(202.5, 1);
    expect(out.stop).toBeCloseTo(192.5, 1);
  });

  it("treats atr14 >= 1 as already-dollar (backward compat)", () => {
    const out = deriveActionBox({
      currentPrice: 200,
      atr14: 4.0,  // dollar value, not ratio
      atrDollar: null,
      analystTarget: 220,
      high180d: null,
      confidence: 0.6,
    });
    expect(out.entryLow).toBeCloseTo(198, 1);
    expect(out.entryHigh).toBeCloseTo(202, 1);
    expect(out.stop).toBeCloseTo(194, 1);
  });

  it("returns nulls when neither atr14 nor atr_dollar is provided", () => {
    const out = deriveActionBox({
      currentPrice: 200,
      atr14: null,
      atrDollar: null,
      analystTarget: 220,
      high180d: null,
      confidence: 0.6,
    });
    expect(out.entryLow).toBeNull();
    expect(out.stop).toBeNull();
    expect(out.target).toBeNull();
    expect(out.rrRatio).toBeNull();
  });
});
