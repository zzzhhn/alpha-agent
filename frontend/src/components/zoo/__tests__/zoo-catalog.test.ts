import { describe, expect, it } from "vitest";
import type { ZooEntry } from "@/lib/factor-zoo";
import { filterZooCatalog } from "../zoo-catalog";

const fixture: ZooEntry[] = [
  { id: "a", name: "Value", expression: "rank(ep)", hypothesis: "", savedAt: "2026-10-21", headlineMetrics: { testSharpe: 0 } },
  { id: "b", name: "Volume", expression: "ts_zscore(volume, 20)", hypothesis: "", savedAt: "2026-10-22", direction: "long_only", headlineMetrics: { testSharpe: 1.1 } },
  { id: "c", name: "Momentum", expression: "rank(returns)", hypothesis: "", savedAt: "2026-10-23" },
  { id: "d", name: "Variance", expression: "rank(volatility)", hypothesis: "", savedAt: "2026-10-24", headlineMetrics: { testSharpe: Infinity } },
];

const query = {
  search: "", direction: "all", status: "all", staleIds: new Set(["b"]),
  sort: "sharpe", order: "desc", locale: "en",
} as const;

describe("Zoo catalog selection", () => {
  it("searches name and expression case-insensitively before filtering or slicing", () => {
    expect(filterZooCatalog(fixture, { ...query, search: "  ZSCORE " }).map(({ id }) => id)).toEqual(["b"]);
    expect(filterZooCatalog(fixture, { ...query, search: "variance" }).map(({ id }) => id)).toEqual(["d"]);
    expect(filterZooCatalog(fixture, { ...query, search: "not present" })).toEqual([]);
  });

  it("keeps absent and nonfinite scores last in both directions, while keeping zero numeric", () => {
    expect(filterZooCatalog(fixture, query).map(({ id }) => id)).toEqual(["b", "a", "c", "d"]);
    expect(filterZooCatalog(fixture, { ...query, order: "asc" }).map(({ id }) => id)).toEqual(["a", "b", "c", "d"]);
    expect(fixture.map(({ id }) => id)).toEqual(["a", "b", "c", "d"]);
  });

  it("combines direction and status filters without treating missing scores as champions", () => {
    expect(filterZooCatalog(fixture, { ...query, status: "champion" }).map(({ id }) => id)).toEqual(["b"]);
    expect(filterZooCatalog(fixture, { ...query, status: "stale", direction: "long_short" })).toEqual([]);
    expect(filterZooCatalog(fixture, { ...query, direction: "long_short" }).map(({ id }) => id)).toEqual(["a", "c", "d"]);
  });
});
