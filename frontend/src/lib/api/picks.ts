// frontend/src/lib/api/picks.ts
import { apiGet, apiPost } from "./client";

export interface BreakdownEntry {
  signal: string;
  z: number;
  weight: number;
  weight_effective: number;
  contribution: number;
  raw: unknown;
  source: string;
  timestamp: string;
  error: string | null;
}

export interface RatingCard {
  ticker: string;
  rating: "BUY" | "OW" | "HOLD" | "UW" | "SELL";
  confidence: number;
  composite_score: number;
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
