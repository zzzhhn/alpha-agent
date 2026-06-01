import { describe, expect, it } from "vitest";

import { computeHiddenDims } from "../GradeStrip";

describe("computeHiddenDims", () => {
  it("hides a dimension that is '—' across every pick", () => {
    const picks = [
      { dimension_grades: { Momentum: "A", Catalyst: "—", Insider: "—" } },
      { dimension_grades: { Momentum: "C", Catalyst: "—", Insider: "—" } },
    ];
    const hidden = computeHiddenDims(picks);
    expect(hidden.has("Catalyst")).toBe(true);
    expect(hidden.has("Insider")).toBe(true);
    expect(hidden.has("Momentum")).toBe(false);
  });

  it("keeps a dimension alive if ANY pick has a real grade", () => {
    const picks = [
      { dimension_grades: { Insider: "—" } },
      { dimension_grades: { Insider: "B" } }, // one real grade -> column stays
    ];
    expect(computeHiddenDims(picks).has("Insider")).toBe(false);
  });

  it("treats a missing dimension key as dead", () => {
    const picks = [{ dimension_grades: { Momentum: "A" } }];
    // Catalyst absent from every pick -> hidden.
    expect(computeHiddenDims(picks).has("Catalyst")).toBe(true);
  });

  it("returns an empty set for no picks (nothing to hide)", () => {
    expect(computeHiddenDims([]).size).toBe(0);
  });
});
