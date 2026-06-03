// frontend/src/lib/api/data_sources.ts
import { apiGet, type ApiGetOptions } from "./client";

export interface DataSourceStat {
  rows: number | null;
  last_fetched_at: string | null;
  error?: string;
}

// Keyed by source id (finnhub / edgar / news / yfinance / fred). A null value
// means "live-fetched, no stored count" (FRED macro).
export interface DataSourcesResponse {
  sources: Record<string, DataSourceStat | null>;
}

export const fetchDataSources = (opts?: ApiGetOptions) =>
  apiGet<DataSourcesResponse>("/api/_health/data_sources", opts);
