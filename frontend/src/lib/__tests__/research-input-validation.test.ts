import { describe, expect, it } from "vitest";
import { researchNumberError, researchParameterErrors } from "../research-input-validation";

describe("research input bounds", () => {
  it("matches supported backend boundaries instead of admitting impossible drafts", () => {
    const valid = { topPct: 1, bottomPct: 50, lookback: 5, transactionCostBps: 200 };
    expect(Object.values(researchParameterErrors(valid, "zh")).some(Boolean)).toBe(false);
    expect(researchNumberError("lookback", 252, "zh")).toBeUndefined();
    for (const [field, value] of [["topPct", 99], ["transactionCostBps", -1], ["lookback", 2000], ["lookback", 12.5], ["bottomPct", NaN]] as const) {
      expect(researchNumberError(field, value, "zh")).toBeTruthy();
    }
  });
});
