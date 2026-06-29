import { describe, it, expect } from "vitest";

import { classifyFactorTier } from "../factor-tier";

// Canonical thresholds (mirrors FactorExamples.tsx):
//   PURE ALPHA   (α-p < 0.05 AND |β| < 0.30)
//   LEVERED ALPHA(α-p < 0.05)
//   MARGINAL     (α-p < 0.10)
//   NOISE        (otherwise)
describe("classifyFactorTier", () => {
  it("PURE ALPHA: significant alpha + low beta", () => {
    expect(classifyFactorTier(0.022, -0.1).label).toBe("PURE ALPHA");
    expect(classifyFactorTier(0.043, 0.03).label).toBe("PURE ALPHA");
  });

  it("LEVERED ALPHA: significant alpha but high beta", () => {
    expect(classifyFactorTier(0.02, 0.9).label).toBe("LEVERED ALPHA");
    expect(classifyFactorTier(0.04, -0.45).label).toBe("LEVERED ALPHA");
  });

  it("MARGINAL: alpha p in [0.05, 0.10)", () => {
    expect(classifyFactorTier(0.06, -0.087).label).toBe("MARGINAL");
    expect(classifyFactorTier(0.077, 1.17).label).toBe("MARGINAL");
  });

  it("NOISE: alpha p >= 0.10", () => {
    expect(classifyFactorTier(0.126, 0.5).label).toBe("NOISE");
    expect(classifyFactorTier(0.418, 0.0).label).toBe("NOISE");
  });

  it("UNKNOWN: missing / non-finite p", () => {
    expect(classifyFactorTier(undefined, 0.1).label).toBe("—");
    expect(classifyFactorTier(null, 0.1).label).toBe("—");
    expect(classifyFactorTier(NaN, 0.1).label).toBe("—");
  });

  it("the |β|<0.30 boundary requires a known beta for PURE", () => {
    // significant p but unknown beta cannot be confirmed market-neutral → LEVERED
    expect(classifyFactorTier(0.02, undefined).label).toBe("LEVERED ALPHA");
    // |β| exactly 0.30 is not < 0.30 → LEVERED
    expect(classifyFactorTier(0.02, 0.3).label).toBe("LEVERED ALPHA");
  });
});
