import { describe, expect, it } from "vitest";
import { evolutionPage, pendingReviewCounts } from "./review-state";

describe("Evolution review counts", () => {
  it("includes both loaded queues and counts only pending proposals", () => {
    const pending = Array.from({ length: 117 }, () => ({ status: "pending" }));
    expect(pendingReviewCounts([{ status: "approved" }], pending)).toEqual({
      policy: 0, methodology: 117, total: 117, known: 117,
    });
  });

  it("distinguishes unavailable from known zero and preserves a known lower bound", () => {
    expect(pendingReviewCounts(null, [{ status: "pending" }])).toEqual({
      policy: null, methodology: 1, total: null, known: 1,
    });
    expect(pendingReviewCounts([], null).total).toBeNull();
    expect(pendingReviewCounts([], []).total).toBe(0);
  });
});

describe("Evolution pagination", () => {
  it.each([30, 50])("keeps all %s loaded change records reachable", (total) => {
    const records = Array.from({ length: total }, (_, index) => index + 1);
    const paginated = Array.from({ length: total / 5 }, (_, index) => evolutionPage(records, index + 1).visible);
    expect(paginated.flat()).toEqual(records);
    expect(evolutionPage(records, 2).visible).toEqual([6, 7, 8, 9, 10]);
  });

  it("clamps to the last valid page when data shrinks", () => {
    expect(evolutionPage([1, 2, 3, 4, 5, 6], 10)).toEqual({ page: 2, visible: [6] });
    expect(evolutionPage([], 10)).toEqual({ page: 1, visible: [] });
  });
});
