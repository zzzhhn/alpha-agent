import type { EquityPoint } from "@/lib/api/paper";

export interface NormalizedEquityPoint extends EquityPoint {
  readonly portfolio_index: number;
}

/** Put portfolio and benchmark on the same 100-based return scale. */
export function normalizePaperCurve(
  series: readonly EquityPoint[],
): readonly NormalizedEquityPoint[] {
  const base = series.find(
    (point) => Number.isFinite(point.portfolio_value) && point.portfolio_value > 0,
  )?.portfolio_value;
  if (!base) return [];
  return series.map((point) => ({
    ...point,
    portfolio_index: (point.portfolio_value / base) * 100,
  }));
}
