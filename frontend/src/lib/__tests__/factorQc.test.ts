import { describe, it, expect } from "vitest";

import { buildSmokeScorecard } from "../factorQc";
import type { SmokeReport } from "../types";

// Minimal SmokeReport with the structural fields the scorecard reads. ic_spearman
// / rows_valid / runtime_ms are diagnostics the scorecard shows but does not grade
// (the synthetic-panel IC is noise, not a predictive verdict — that's the backtest).
function report(overrides: Partial<SmokeReport> = {}): SmokeReport {
  return {
    rows_valid: 200,
    ic_spearman: 0.01,
    runtime_ms: 1,
    factor_std: 0.3,
    degenerate: false,
    turnover: 0.05,
    high_turnover: false,
    robustness: 0.95,
    low_robustness: false,
    ...overrides,
  };
}

describe("buildSmokeScorecard", () => {
  it("a clean factor passes every structural check", () => {
    const sc = buildSmokeScorecard(report());
    expect(sc.verdict).toBe("pass");
    expect(sc.integrity).toBe("pass");
    expect(sc.stability).toBe("pass");
    expect(sc.robustness).toBe("pass");
  });

  it("a degenerate factor blocks (integrity = block, verdict = block)", () => {
    const sc = buildSmokeScorecard(report({ degenerate: true }));
    expect(sc.integrity).toBe("block");
    expect(sc.verdict).toBe("block");
  });

  it("high turnover is an advisory caution, not a block", () => {
    const sc = buildSmokeScorecard(report({ high_turnover: true, turnover: 2.7 }));
    expect(sc.stability).toBe("caution");
    expect(sc.verdict).toBe("caution");
    expect(sc.integrity).toBe("pass");
  });

  it("low robustness is an advisory caution, not a block", () => {
    const sc = buildSmokeScorecard(report({ low_robustness: true, robustness: 0.1 }));
    expect(sc.robustness).toBe("caution");
    expect(sc.verdict).toBe("caution");
  });

  it("block dominates caution when a factor trips both", () => {
    const sc = buildSmokeScorecard(
      report({ degenerate: true, high_turnover: true, low_robustness: true })
    );
    expect(sc.verdict).toBe("block");
  });

  it("treats missing optional flags as passing (resilient to old responses)", () => {
    const sc = buildSmokeScorecard({
      rows_valid: 200,
      ic_spearman: 0.01,
      runtime_ms: 1,
    });
    expect(sc.verdict).toBe("pass");
    expect(sc.stability).toBe("pass");
    expect(sc.robustness).toBe("pass");
  });
});
