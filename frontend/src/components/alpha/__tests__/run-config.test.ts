import { describe, expect, it } from "vitest";
import { alphaRunConfig, sameAlphaValidation } from "../run-config";
import type { AlphaValidationParams } from "../useAlphaChain";

const submitted: AlphaValidationParams = {
  direction: "short_only", topPct: 15, neutralize: "sector",
  transactionCostBps: 25, benchmarkTicker: "RSP",
};

describe("Alpha run snapshot handoff", () => {
  it("preserves every submitted parameter for Zoo and Backtest", () => {
    expect(alphaRunConfig(submitted)).toEqual({
      direction: "short_only", topPct: 0.15, bottomPct: 0.15,
      neutralize: "sector", transactionCostBps: 25,
      benchmarkTicker: "RSP", mode: "static",
    });
  });
  it("distinguishes an edited draft without changing the submitted snapshot", () => {
    const draft = { ...submitted, topPct: 30 };
    expect(sameAlphaValidation(submitted, draft)).toBe(false);
    expect(sameAlphaValidation(submitted, { ...submitted })).toBe(true);
    expect(alphaRunConfig(submitted).topPct).toBe(0.15);
  });
});
