import { describe, expect, it } from "vitest";

import type { RatingCard } from "@/lib/api/picks";
import { buildAttributionDimensions } from "@/lib/attribution-dimensions";

function card(overrides: Partial<RatingCard>): RatingCard {
  return {
    ticker: "TEST",
    rating: "HOLD",
    confidence: 0.5,
    composite_score: 0,
    as_of: "2026-08-27T00:00:00Z",
    breakdown: [],
    top_drivers: [],
    top_drags: [],
    ...overrides,
  };
}

describe("buildAttributionDimensions", () => {
  it("always returns the canonical six dimensions in stable order", () => {
    const values = buildAttributionDimensions(card({ dimension_scores: {} }));
    expect(values.map((value) => value.key)).toEqual([
      "Momentum", "Technical", "Sentiment", "Catalyst", "Insider", "Flow",
    ]);
  });

  it("distinguishes a real neutral zero from an unavailable dimension", () => {
    const values = buildAttributionDimensions(card({
      dimension_scores: { Momentum: 0, Technical: null },
    }));
    expect(values[0]).toMatchObject({ key: "Momentum", score: 0, available: true });
    expect(values[1]).toMatchObject({ key: "Technical", score: null, available: false });
  });

  it("does not mislabel raw signal averages as normalized dimension scores", () => {
    const values = buildAttributionDimensions(card({
      breakdown: [{
        signal: "earnings",
        z: 1.2,
        weight: 0,
        weight_effective: 0,
        contribution: 0,
        raw: {},
        source: "fixture",
        timestamp: "2026-08-27T00:00:00Z",
        error: null,
      }],
      dimension_grades: { Catalyst: "A", Flow: "—" },
    }));
    expect(values.find((value) => value.key === "Catalyst")).toMatchObject({
      score: null,
      available: false,
    });
    expect(values.find((value) => value.key === "Flow")?.available).toBe(false);
  });
});
