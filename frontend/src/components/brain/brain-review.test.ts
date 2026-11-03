import { describe, expect, it } from "vitest";
import { DEFAULT_BRAIN_PAGE_SIZE, brainSubmissionState, familyLabel, hasUnsimulatedCandidates, nextExpandedAlpha, runFailureAction } from "./brain-review";

describe("BRAIN run review", () => {
  it("distinguishes rejected submissions from acceptance in both receipts and persisted rows", () => {
    const submitted_at = "2026-11-03T00:00:00Z";
    expect(brainSubmissionState({ ok: false })).toBe("rejected");
    expect(brainSubmissionState({ ok: true })).toBe("accepted");
    expect(brainSubmissionState({ submitted_at, brain_status: "submit_rejected" })).toBe("rejected");
    expect(brainSubmissionState({ submitted_at, brain_status: "submitted" })).toBe("accepted");
    expect(brainSubmissionState({ submitted_at, brain_status: null })).toBe("attempted");
  });
  it("uses ten rows by default and opens only one result at a time", () => {
    expect(DEFAULT_BRAIN_PAGE_SIZE).toBe(10);
    expect(nextExpandedAlpha(null, 160)).toBe(160);
    expect(nextExpandedAlpha(160, 161)).toBe(161);
    expect(nextExpandedAlpha(161, 161)).toBeNull();
  });

  it("opens candidate audit for generated candidates with zero simulations", () => {
    expect(hasUnsimulatedCandidates({ id: 160, generated_n: 16, simulated_n: 0 })).toBe(true);
    expect(hasUnsimulatedCandidates({ id: 160, generated_n: 16, simulated_n: 8 })).toBe(false);
    expect(hasUnsimulatedCandidates({ id: 160, generated_n: 0, simulated_n: 0 })).toBe(false);
    expect(hasUnsimulatedCandidates({ id: 160, generated_n: 16, simulated_n: null })).toBe(false);
    expect(hasUnsimulatedCandidates(null)).toBe(false);
  });

  it("localizes known families without inventing labels for new IDs", () => {
    expect(familyLabel("iv_term", true)).toBe("隐波期限结构");
    expect(familyLabel("iv_term", false)).toBe("IV term");
    expect(familyLabel(null, true)).toBe("混合家族");
    expect(familyLabel("future_family", true)).toBe("future_family");
  });

  it("summarizes dispatch failures without showing raw diagnostics", () => {
    expect(runFailureAction({ id: 160, error_detail: "GitHub API 422: raw response" }, false))
      .toContain("could not be dispatched");
    expect(runFailureAction({ id: 160, error_detail: "GitHub API 422: raw response" }, false))
      .not.toContain("raw response");
    expect(runFailureAction({ id: 160 }, false)).not.toContain("No candidates were generated");
  });
});
