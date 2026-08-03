import { describe, expect, it } from "vitest";

import { evaluateBacktestGates } from "../backtest-gates";

const thresholds = {
  sharpe: 1,
  maxDD: -0.15,
  ic: 0.02,
  turnover: 0.4,
  annReturn: 0.1,
};

describe("evaluateBacktestGates", () => {
  it("respects metric direction and missing evidence", () => {
    const gates = evaluateBacktestGates({
      sharpe: 1.2,
      maxDD: -0.2,
      ic: 0.03,
      turnover: 0.55,
      annReturn: null,
    }, thresholds);

    expect(gates.map((gate) => gate.status)).toEqual([
      "pass",
      "fail",
      "pass",
      "fail",
      "missing",
    ]);
  });
});
