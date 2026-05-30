// frontend/src/lib/__tests__/evolution-health.test.ts
// Locks the self-evolution health verdicts that drive the top-of-page strip.
// The thresholds encode their own justification (rule 9):
//   - Brier >= 0.25 is the no-skill baseline (always predict 0.5 at a 50%
//     base rate) — at/above it the calibration is no better than guessing.
//   - High-confidence buckets are "overconfident" when predicted exceeds
//     actual hit rate by > 0.08 on average.
// Matches the real 2026-05-30 production read (Brier 0.2842, overconfident
// high-end → calibration warns).
import { describe, it, expect } from "vitest";
import {
  assessCalibration,
  assessIc,
  assessWeights,
  assessProposals,
} from "@/lib/evolution-health";
import type {
  EvolutionCalibration,
  IcTrendResponse,
  EvolutionWeightsResponse,
  ProposalsResponse,
} from "@/lib/api/evolution";

describe("assessCalibration", () => {
  it("warns when worse than the no-skill Brier baseline", () => {
    const cal: EvolutionCalibration = {
      as_of: "2026-05-30",
      n_pairs: 549,
      applied: true,
      buckets: [
        { lo: 0.0, hi: 0.2, hit_rate: 0.17, brier: 0.28, n: 100 },
        { lo: 0.6, hi: 0.8, hit_rate: 0.65, brier: 0.29, n: 120 },
        { lo: 0.8, hi: 1.0, hit_rate: 0.3, brier: 0.3, n: 80 },
      ],
    };
    const v = assessCalibration(cal);
    expect(v.tone).toBe("warn");
    expect(v.facts.worseThanGuess).toBe(true);
    // predicted 0.7 vs actual 0.65, predicted 0.9 vs actual 0.30 → overconf
    expect(v.facts.overconfident).toBe(true);
  });

  it("is good when well below no-skill and not overconfident", () => {
    const cal: EvolutionCalibration = {
      as_of: "2026-05-30",
      n_pairs: 600,
      applied: true,
      buckets: [
        { lo: 0.6, hi: 0.8, hit_rate: 0.72, brier: 0.12, n: 120 },
        { lo: 0.8, hi: 1.0, hit_rate: 0.91, brier: 0.1, n: 80 },
      ],
    };
    expect(assessCalibration(cal).tone).toBe("good");
  });

  it("is neutral while still accumulating (not applied)", () => {
    const cal: EvolutionCalibration = {
      as_of: null,
      n_pairs: 30,
      applied: false,
      buckets: [],
    };
    const v = assessCalibration(cal);
    expect(v.tone).toBe("neutral");
    expect(v.facts.applied).toBe(false);
  });

  it("reports na when calibration is missing", () => {
    expect(assessCalibration(null).tone).toBe("na");
  });
});

describe("assessIc", () => {
  it("uses the chronologically latest point per signal", () => {
    const ic: IcTrendResponse = {
      window_days: 30,
      series: [
        {
          signal_name: "analyst",
          points: [
            { computed_at: "2026-05-20", ic: -0.1, n: 50 },
            { computed_at: "2026-05-29", ic: 0.21, n: 50 }, // latest positive
          ],
        },
        {
          signal_name: "factor",
          points: [{ computed_at: "2026-05-29", ic: -0.2, n: 50 }],
        },
      ],
    };
    const v = assessIc(ic);
    expect(v.facts.pos).toBe(1);
    expect(v.facts.total).toBe(2);
    expect(v.facts.strongestName).toBe("analyst");
  });
});

describe("assessWeights", () => {
  it("warns when a live signal is degrading", () => {
    const w: EvolutionWeightsResponse = {
      weights: [
        {
          signal_name: "factor",
          status: "live",
          weight: 0.1,
          reason: null,
          consecutive_bad_windows: 2,
          shadow_streak: 0,
          last_updated: null,
        },
      ],
    };
    expect(assessWeights(w).tone).toBe("warn");
  });

  it("is neutral when shadows merely accumulate", () => {
    const w: EvolutionWeightsResponse = {
      weights: [
        {
          signal_name: "analyst",
          status: "shadow",
          weight: 0.23,
          reason: "shadow_candidate",
          consecutive_bad_windows: 0,
          shadow_streak: 0,
          last_updated: null,
        },
      ],
    };
    expect(assessWeights(w).tone).toBe("neutral");
  });
});

describe("assessProposals", () => {
  it("flags action when proposals are pending", () => {
    const p: ProposalsResponse = {
      proposals: [
        { id: 1, field: "x", old_value: 1, new_value: 2, evidence: {}, changed_at: "", status: "pending" },
      ],
    };
    expect(assessProposals(p).tone).toBe("action");
  });

  it("is neutral when nothing is pending", () => {
    expect(assessProposals({ proposals: [] }).tone).toBe("neutral");
  });
});
