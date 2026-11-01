import { describe, expect, it } from "vitest";
import { consistencyEvidence } from "../picks-evidence";

describe("visible recommendation evidence", () => {
  it("distinguishes absent metadata from zero samples", () => {
    expect(consistencyEvidence({}, "d5", "zh").sampleLabel).toBe("n=?");
    expect(consistencyEvidence({ consistency_n: { d5: 0 } }, "d5", "zh").sampleLabel).toBe("n=0/3");
  });
  it("preserves a real zero hit rate", () => {
    const evidence = consistencyEvidence({ consistency: { d5: 0, m1: null, y1: null, hist: null }, consistency_n: { d5: 4 } }, "d5", "en");
    expect(evidence.pct).toBe(0);
    expect(evidence.sampleLabel).toBe("n=4");
  });
  it("does not inflate a thin sample into a displayed rate", () => {
    const evidence = consistencyEvidence({ consistency: { d5: 1, m1: null, y1: null, hist: null }, consistency_n: { d5: 1 } }, "d5", "zh");
    expect(evidence.pct).toBeNull();
    expect(evidence.reason).toContain("至少需要 3 条");
  });
  it("explains an unavailable statistic with adequate samples separately", () => {
    const evidence = consistencyEvidence({ consistency_n: { m1: 12 } }, "m1", "en");
    expect(evidence.reason).toContain("no valid rate");
    expect(evidence.pct).toBeNull();
  });
});
