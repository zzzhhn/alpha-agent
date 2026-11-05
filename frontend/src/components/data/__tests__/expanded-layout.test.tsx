import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { UniverseCoverage, UniverseOverview } from "../UniverseCard";
import { OperandCatalog } from "../OperandCatalog";
import type { CoverageResponse, UniverseInfo } from "@/lib/types";

const coverage: CoverageResponse = {
  universe_id: "test", n_tickers: 20, n_days: 10, start_date: "2026-10-01", end_date: "2026-10-15",
  ohlcv_total_cells: 200, ohlcv_missing_cells: 10, ohlcv_coverage_pct: 95,
  field_coverage: Array.from({ length: 18 }, (_, index) => ({
    name: `field_${index}`, category: "fundamental", tier: "T1", fill_rate: .9, n_present: 180, n_total: 200,
  })), ticker_coverage: [],
};
const universe: UniverseInfo = {
  id: "test", name: "Test universe", ticker_count: 20, benchmark: "SPY", tickers: [],
  start_date: "2026-10-01", end_date: "2026-10-15", n_days: 10, currency: "USD",
};

describe("expanded workspace layout contracts", () => {
  it("keeps the overview independent of variable-length coverage evidence", () => {
    const html = renderToStaticMarkup(<UniverseOverview universe={universe} closePct={95} />);
    expect(html).toContain("95.00%");
    expect(html).not.toContain("<details");
  });
  it("bounds a long coverage group to eight fields and retains its full count", () => {
    const html = renderToStaticMarkup(<UniverseCoverage coverage={coverage} />);
    expect(html).toContain("18 个字段");
    expect(html).toContain("1 / 3");
    expect((html.match(/<code\b/g) ?? []).length).toBe(8);
    expect(html).toMatch(/<details name="[^"]+"/);
    expect(html).not.toContain("field_17");
  });
  it("opens directory evidence outside the equal-height tile grid", () => {
    const html = renderToStaticMarkup(<OperandCatalog catalog={{
      operators: [{ name: "rank", category: "cross_section", tier: "T1", implemented: true, description_zh: "长说明".repeat(100) }],
      operands: [], tier_summary: { operators: { total: 1, T1: 1, T2: 0, T3: 0 }, operands: { total: 0, T1: 0, T2: 0, T3: 0 } },
    }} />);
    expect(html).toContain('aria-haspopup="dialog"');
    expect(html).not.toContain("<details");
    expect(html).not.toContain("长说明");
  });
});
