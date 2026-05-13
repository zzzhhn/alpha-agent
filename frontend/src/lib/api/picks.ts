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
}

export const fetchPicks = (limit = 20) =>
  apiGet<{ picks: RatingCard[]; as_of: string | null; stale: boolean }>(
    `/api/picks/lean?limit=${limit}`,
  );

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
