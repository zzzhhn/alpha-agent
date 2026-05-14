// frontend/src/lib/api/picks.ts
import { apiGet, apiPost } from "./client";

export interface BreakdownEntry {
  signal: string;
  // Numeric fields may be null when the backend's NaN sanitizer mapped an
  // unrepresentable IEEE 754 value (NaN/Inf from a degenerate signal) to
  // JSON null. Components must handle null defensively (use `?? 0`).
  z: number | null;
  weight: number | null;
  weight_effective: number | null;
  contribution: number | null;
  raw: unknown;
  source: string;
  timestamp: string;
  error: string | null;
}

export interface RatingCard {
  ticker: string;
  rating: "BUY" | "OW" | "HOLD" | "UW" | "SELL";
  // Same nullable contract as BreakdownEntry — composite/confidence
  // may arrive as null when DB column held NaN before storage-side fix
  // landed (legacy rows). Components must coalesce.
  confidence: number | null;
  composite_score: number | null;
  as_of: string;
  breakdown: BreakdownEntry[];
  top_drivers: string[];
  top_drags: string[];
  // True for a slow-only row: daily-pipeline data with rating/confidence
  // derived (no fast factors), can be up to ~1 day old. Absent on the
  // single-card /api/stock response, hence optional.
  partial?: boolean;
}

export const fetchPicks = (limit = 50, search?: string) => {
  const params = new URLSearchParams({ limit: String(limit) });
  const q = search?.trim();
  if (q) params.set("search", q);
  return apiGet<{ picks: RatingCard[]; as_of: string | null; stale: boolean }>(
    `/api/picks/lean?${params.toString()}`,
  );
};

export const fetchStock = (ticker: string) =>
  apiGet<{ card: RatingCard; stale: boolean }>(
    `/api/stock/${ticker.toUpperCase()}`,
  );

export interface BriefRequest {
  mode: "lean" | "rich";
  llm_provider?: string;
  api_key?: string;
}

export const postBrief = (ticker: string, body: BriefRequest) =>
  apiPost<
    {
      ticker: string;
      rating: string;
      thesis: { bull: string[]; bear: string[] };
      rendered_at: string;
    },
    BriefRequest
  >(`/api/brief/${ticker.toUpperCase()}`, body);

// frontend/src/lib/api/picks.ts (additions — append after postBrief)

/**
 * Expected shape of `breakdown[signal="factor"].raw` after M4a. Block
 * components cast via `raw as FactorRaw | null`; legacy rows from before
 * the signal enrichment may still have raw=float, so the cast is unsafe —
 * the block must check `typeof raw === "object" && raw !== null` first.
 */
export interface FundamentalsData {
  pe_trailing: number | null;
  pe_forward: number | null;
  eps_ttm: number | null;
  market_cap: number | null;
  dividend_yield: number | null;
  profit_margin: number | null;
  debt_to_equity: number | null;
  beta: number | null;
}

export interface FactorRaw {
  z: number;
  fundamentals: FundamentalsData | null;
}

export interface NewsItem {
  title: string;
  publisher: string;
  published_at: string; // ISO 8601
  link: string;
  sentiment: "pos" | "neg" | "neu";
}

export interface NewsRaw {
  n: number;
  mean_sent: number;
  headlines: NewsItem[];
}

export interface EarningsRaw {
  surprise_pct: number | null;
  days_to_earnings: number | null;
  next_date: string | null; // YYYY-MM-DD
  days_until: number | null;
  eps_estimate: number | null;
  revenue_estimate: number | null;
}

export interface OhlcvBar {
  date: string; // YYYY-MM-DD
  // Backend (yf_helpers.extract_ohlcv post A1 fix) propagates null when
  // yfinance returned NaN/missing prices. Chart consumer (Task E1) must
  // drop or gap-fill the bar.
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number;
}

export interface OhlcvResponse {
  ticker: string;
  period: string;
  bars: OhlcvBar[];
}

export const fetchOhlcv = (ticker: string, period = "6mo") =>
  apiGet<OhlcvResponse>(
    `/api/stock/${ticker.toUpperCase()}/ohlcv?period=${period}`,
  );
