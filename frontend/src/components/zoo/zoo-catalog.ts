import { readDirection, type ZooDirection, type ZooEntry } from "@/lib/factor-zoo";

export type ZooSortColumn = "name" | "sharpe" | "return" | "ic" | "savedAt";
export type ZooSortDirection = "asc" | "desc";
export type ZooStatusFilter = "all" | "stale" | "champion";
export type ZooDirectionFilter = "all" | ZooDirection;

export function isFiniteZooMetric(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function sortValue(entry: ZooEntry, column: Exclude<ZooSortColumn, "name">) {
  switch (column) {
    case "sharpe": return entry.headlineMetrics?.testSharpe;
    case "return": return entry.headlineMetrics?.totalReturn;
    case "ic": return entry.headlineMetrics?.testIc;
    case "savedAt": return new Date(entry.savedAt).getTime();
  }
}

export function filterZooCatalog(
  entries: readonly ZooEntry[],
  query: {
    readonly search: string;
    readonly direction: ZooDirectionFilter;
    readonly status: ZooStatusFilter;
    readonly staleIds: ReadonlySet<string>;
    readonly sort: ZooSortColumn;
    readonly order: ZooSortDirection;
    readonly locale: "zh" | "en";
  },
): ZooEntry[] {
  const search = query.search.trim().toLowerCase();
  const sign = query.order === "asc" ? 1 : -1;

  return entries.filter((entry) => {
    if (search && ![entry.name, entry.expression].some((value) => value.toLowerCase().includes(search))) {
      return false;
    }
    if (query.direction !== "all" && readDirection(entry) !== query.direction) return false;
    if (query.status === "stale" && !query.staleIds.has(entry.id)) return false;
    const sharpe = entry.headlineMetrics?.testSharpe;
    if (query.status === "champion" && !(isFiniteZooMetric(sharpe) && sharpe >= 1)) return false;
    return true;
  }).sort((a, b) => {
    if (query.sort === "name") return sign * a.name.localeCompare(b.name, query.locale);
    const first = sortValue(a, query.sort);
    const second = sortValue(b, query.sort);
    // Missing is not a low score, including when the user sorts ascending.
    if (!isFiniteZooMetric(first)) return isFiniteZooMetric(second) ? 1 : 0;
    if (!isFiniteZooMetric(second)) return -1;
    return sign * (first - second);
  });
}
