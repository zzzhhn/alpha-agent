import { describe, expect, it } from "vitest";
import { shouldChartPaperCurve } from "@/lib/paper-curve";

describe("shouldChartPaperCurve", () => {
  it("does not chart a cash-only account against SPY", () => {
    expect(shouldChartPaperCurve({ positions: [], pending_orders: 0, realized_pnl: 0 })).toBe(false);
  });

  it("charts once a position, pending order or realized result exists", () => {
    expect(shouldChartPaperCurve({ positions: [{}] })).toBe(true);
    expect(shouldChartPaperCurve({ positions: [], pending_orders: 1 })).toBe(true);
    expect(shouldChartPaperCurve({ positions: [], realized_pnl: -12.5 })).toBe(true);
  });

  it("keeps the existing chart when the account is unknown", () => {
    expect(shouldChartPaperCurve(null)).toBe(true);
  });
});
