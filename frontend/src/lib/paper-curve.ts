import type { EquityPoint } from "@/lib/api/paper";

export interface NormalizedEquityPoint extends EquityPoint {
  readonly portfolio_index: number | null;
}

/** Put portfolio and benchmark on the same 100-based return scale. */
export function normalizePaperCurve(
  series: readonly EquityPoint[],
): readonly NormalizedEquityPoint[] {
  const base = series.find(
    (point) => point.portfolio_value !== null && Number.isFinite(point.portfolio_value) && point.portfolio_value > 0,
  )?.portfolio_value;
  if (!base) return [];
  return series.map((point) => ({
    ...point,
    portfolio_index: point.portfolio_value !== null && Number.isFinite(point.portfolio_value)
      ? (point.portfolio_value / base) * 100
      : null,
    benchmark_index: point.benchmark_index !== null && Number.isFinite(point.benchmark_index)
      ? point.benchmark_index
      : null,
  }));
}

/**
 * A cash-only account has a flat 100 line by construction; plotting it against
 * SPY reads as underperformance that never involved a decision. Only chart
 * once the account has held a position or has an order in flight.
 */
export function shouldChartPaperCurve(account: {
  readonly positions: readonly unknown[];
  readonly pending_orders?: number;
  readonly realized_pnl?: number | null;
} | null): boolean {
  if (!account) return true;
  return account.positions.length > 0 || (account.pending_orders ?? 0) > 0 || (account.realized_pnl ?? 0) !== 0;
}
