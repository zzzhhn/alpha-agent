import type { RatingCard } from "@/lib/api/picks";

export const ATTRIBUTION_DIMENSIONS = [
  { key: "Momentum", signals: ["factor"], labelKey: "radar.dimension_momentum" },
  { key: "Technical", signals: ["technicals"], labelKey: "radar.dimension_technical" },
  {
    key: "Sentiment",
    signals: ["news", "political_impact", "geopolitical_impact"],
    labelKey: "radar.dimension_sentiment",
  },
  { key: "Catalyst", signals: ["earnings", "calendar"], labelKey: "radar.dimension_catalyst" },
  { key: "Insider", signals: ["insider"], labelKey: "radar.dimension_insider" },
  { key: "Flow", signals: ["options", "premarket", "macro"], labelKey: "radar.dimension_flow" },
] as const;

export type AttributionDimensionKey = (typeof ATTRIBUTION_DIMENSIONS)[number]["key"];

export interface AttributionDimensionValue {
  readonly key: AttributionDimensionKey;
  readonly labelKey: (typeof ATTRIBUTION_DIMENSIONS)[number]["labelKey"];
  readonly score: number | null;
  readonly available: boolean;
}

/**
 * Build the fixed six-dimension radar contract.
 *
 * New API responses provide cross-sectionally standardized dimension_scores.
 * Raw signal averages are not cross-sectionally normalized. Older API
 * responses must show unavailable scores instead of pretending they are on
 * the same scale as the server's dimension scores.
 */
export function buildAttributionDimensions(card: RatingCard): AttributionDimensionValue[] {
  return ATTRIBUTION_DIMENSIONS.map((dimension) => {
    const serverScore = card.dimension_scores?.[dimension.key];
    const score = typeof serverScore === "number" && Number.isFinite(serverScore)
      ? serverScore
      : null;
    return { key: dimension.key, labelKey: dimension.labelKey, score, available: score !== null };
  });
}
